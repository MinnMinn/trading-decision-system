"""THE reader for docs/architecture/providers.json -- the single source of truth for provider identity
(CLAUDE.md §2). Import this; never hard-code a connector path, a venue name or a vendor's identity.

    import providers as P
    P.adapter("binance_futures")        -> '/abs/path/scripts/binance-futures-testnet-order.sh'
    P.for_role("execution", "crypto")   -> ['binance_spot', 'binance_futures']
    P.for_role("market_data", "cfd")    -> ['mt5_bridge']
    P.venue_of("binance_futures")       -> 'binance'
    P.is_live("coinglass")              -> False        # mock_only

Why a registry at all: before it, `crypto` meant Binance by hard-coded script path -- scripts/strategy-runner.py
carried ORDER/MT5/FETCH as module constants, so a different venue meant editing the live order engine.
CLAUDE.md §2 forbids that, and requires market-data / analytics / aggregated-intelligence / execution to be
independently choosable. This module makes provider identity data. It does NOT yet make venue ROUTING data --
scripts/strategy-runner.py still branches on `if venue == "mt5"` in a dozen places; that is CLAUDE.md §4 work
and is tracked in SYSTEM-DESIGN.md §16.1 rather than pretended away here.

Loading validates the two things a registry of external dependencies can actually be wrong about:
  1. A declared adapter that does not exist on disk. A registry naming a connector that was renamed or deleted
     is worse than no registry -- it reads as evidence that a path is live (rules/reduce-hallucinations.md).
  2. A role or market nobody declared. Markets are cross-checked against docs/architecture/instruments.json,
     which owns the market vocabulary; a typo'd market would otherwise make a provider silently unreachable.
Both raise at import, in the repo's fail-loud idiom (cf. scripts/trading_env.py's _read_max_risk_pct, which
refuses rather than guessing).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
# instruments.py owns the market vocabulary and must NOT import this module back -- that direction would
# cycle. Checked before adding the import: instruments.py imports nothing from this repo.
import instruments as I

PATH = os.path.join(ROOT, "docs", "architecture", "providers.json")


def _validate(d):
    roles = {r for r in d["roles"] if not r.startswith("_")}
    statuses = {s for s in d["status_values"] if not s.startswith("_")}
    caps = {c for c in d.get("capabilities", {}) if not c.startswith("_")}
    known_markets = set(I.MARKETS)
    for pid, p in d["providers"].items():
        unknown_roles = [r for r in p["roles"] if r not in roles]
        if unknown_roles:
            raise ValueError(f"{PATH}: provider '{pid}' declares unknown role(s) {unknown_roles}; "
                             f"known roles: {sorted(roles)} (CLAUDE.md §2).")
        if not p["roles"]:
            raise ValueError(f"{PATH}: provider '{pid}' declares no role. A provider with no role cannot be "
                             f"chosen for anything and would sit in the registry as decoration.")
        unknown_markets = [m for m in p["markets"] if m not in known_markets]
        if unknown_markets:
            raise ValueError(f"{PATH}: provider '{pid}' names market(s) {unknown_markets} that "
                             f"docs/architecture/instruments.json does not declare; known: "
                             f"{sorted(known_markets)}. instruments.json owns the market vocabulary.")
        if p["status"] not in statuses:
            raise ValueError(f"{PATH}: provider '{pid}' has status {p['status']!r}; known: {sorted(statuses)}.")
        for key in ("adapter", "market_data_adapter"):
            rel = p.get(key)
            if rel is None:
                continue
            if not os.path.exists(os.path.join(ROOT, rel)):
                raise ValueError(
                    f"{PATH}: provider '{pid}' declares {key} {rel!r}, which does not exist. A registry that "
                    f"names a missing connector reads as evidence that the path is live; fix the path or set "
                    f"it to null and mark the provider `not_built`.")
        # A provider that can receive orders and one that merely informs are different risks. Saying so here
        # keeps CLAUDE.md §4's separation checkable rather than a convention.
        # Checked after the adapter paths above, before the role-specific claims below: a provider with both a
        # dead connector and a missing capability list should report the connector first, because that is the
        # line whose fix is unambiguous. CLAUDE.md §6: capabilities are EXPLICIT -- an absent list is not
        # "unknown, probably fine", it is an unanswered question about a dependency, and "none" is written [].
        declared = p.get("capabilities")
        if not isinstance(declared, list):
            raise ValueError(f"{PATH}: provider '{pid}' declares no `capabilities` list. State what it "
                             f"actually supplies, or `[]` -- never leave it implicit (CLAUDE.md §6).")
        unknown_caps = [c for c in declared if c not in caps]
        if unknown_caps:
            raise ValueError(f"{PATH}: provider '{pid}' declares capability/capabilities {unknown_caps} that "
                             f"the vocabulary does not define; known: {sorted(caps)}. Add it to `capabilities` "
                             f"with a description first -- inventing one at the point of use is how a "
                             f"capability nobody verified becomes load-bearing.")

        if "execution" in p["roles"]:
            if "order_submission" not in declared:
                raise ValueError(f"{PATH}: provider '{pid}' has the execution role but does not declare the "
                                 f"`order_submission` capability. The role and the capability must agree.")
            if p.get("adapter") is None:
                raise ValueError(f"{PATH}: provider '{pid}' claims the execution role with no adapter. An "
                                 f"execution provider that cannot be called is a claim, not a capability.")
            if not p.get("execution_alias"):
                raise ValueError(f"{PATH}: execution provider '{pid}' declares no `execution_alias` -- the "
                                 f"short id its orders, state rows and logs are tagged with.")
            # Whether a HUMAN must be in the loop is a permission, and permissions belong in the registry
            # rather than in whichever caller happens to be running. Without it, an unattended loop picking an
            # execution provider has no way to tell a manual-confirmation venue from its own.
            # What a contract on this venue IS, in the canonical vocabulary (CLAUDE.md §5). Declared per
            # PROVIDER and not per symbol because it is a property of (instrument, venue): BTCUSDT is SPOT on
            # binance_spot and PERPETUAL on binance_futures. Note the deliberate mismatch with the alias --
            # Binance's product is called "futures" and the alias keeps that word because state files and logs
            # are tagged with it, but the contract has no expiry, so its canonical type is PERPETUAL. Letting
            # the provider's word be the domain's word is precisely what §5 forbids.
            mt = p.get("market_type")
            if mt not in I.MARKET_TYPES:
                raise ValueError(f"{PATH}: execution provider '{pid}' has market_type {mt!r}; the canonical "
                                 f"vocabulary is {list(I.MARKET_TYPES)} (docs/architecture/instruments.json "
                                 f"`market_types`).")
            for m in p["markets"]:
                if mt not in I.market_types(m):
                    raise ValueError(
                        f"{PATH}: provider '{pid}' offers {mt} on market '{m}', which declares "
                        f"{I.market_types(m)}. Either the market cannot be traded that way or its "
                        f"`market_types` is incomplete -- both are real answers, guessing is not.")
            if not isinstance(p.get("unattended"), bool):
                raise ValueError(f"{PATH}: execution provider '{pid}' has no boolean `unattended`. Say whether "
                                 f"the unattended pilot may submit through it, or a loop with no human in it "
                                 f"could select a venue whose whole safety story is a human confirmation "
                                 f"(CLAUDE.md §51).")
        # Checked LAST, after every fault that points at a wrong PATH or a wrong CLAIM. Same reasoning as
        # scripts/methods.py's "display text is checked last": a provider with both a missing connector and a
        # missing flag should report the connector, because that is the line the author needs to fix.
        #
        # `external` separates a VENDOR boundary from in-repo cohesion, and the distinction earns its keep:
        # the no-hard-coding rule applies to vendors, not to modules importing their siblings. Without this
        # flag, declaring the repo's own scanner as the analytics provider made scripts/live_rules.py:34 --
        # which loads ict-scan.py as an in-repo module, entirely correctly -- look like a §2 violation.
        if not isinstance(p.get("external"), bool):
            raise ValueError(f"{PATH}: provider '{pid}' has no boolean `external`. Say whether this is a "
                             f"third-party dependency (true) or this repo's own code wearing a provider role "
                             f"(false); the hard-coding ban applies only to the former.")


def _load():
    with open(PATH, encoding="utf-8") as fh:
        d = json.load(fh)
    _validate(d)
    return d


_DATA = _load()
ROLES = tuple(r for r in _DATA["roles"] if not r.startswith("_"))
CAPABILITIES = tuple(c for c in _DATA["capabilities"] if not c.startswith("_"))
STATUS_VALUES = tuple(s for s in _DATA["status_values"] if not s.startswith("_"))
PROVIDERS = _DATA["providers"]
ALL = tuple(PROVIDERS)

# CLAUDE.md §23's vocabulary for how a provider's figures relate to venues. The registry has declared these
# since the §7 work; nothing READ them, so a provider could carry a scope no one had defined and §23's
# "never present an aggregate as one venue's figure" would have had nothing to test against.
AGGREGATION_SCOPES = tuple(s for s in _DATA["aggregation_scopes"] if not s.startswith("_"))
for _pid, _p in PROVIDERS.items():
    if _pid.startswith("_"):
        continue
    _scope = _p.get("aggregation_scope")
    if _scope not in AGGREGATION_SCOPES:
        raise ValueError(f"{PATH}: provider {_pid} declares aggregation_scope {_scope!r}; the vocabulary is "
                         f"{list(AGGREGATION_SCOPES)}. A provider whose scope is unknown cannot be presented "
                         f"honestly (CLAUDE.md §23) -- a reader would have to guess whether its figures are "
                         f"one venue's or many, and guessing is the misattribution §23 forbids.")
    if _scope == "multi_venue" and not _p.get("underlying_venues"):
        raise ValueError(f"{PATH}: provider {_pid} aggregates across venues but names none. CLAUDE.md §23 "
                         f"requires underlying_venues; where the vendor has not disclosed them the honest "
                         f"value is ['UNDECLARED'], never an empty list that reads as 'checked, none'.")


def provider(pid):
    """The raw record. Raises KeyError on an unknown id -- callers validate first."""
    return PROVIDERS[pid]


def adapter(pid):
    """Absolute path to the provider's connector, or None when it has none (mock_only / not_built)."""
    rel = PROVIDERS[pid].get("adapter")
    return os.path.join(ROOT, rel) if rel else None


def market_data_adapter(pid):
    """Absolute path to the provider's market-data connector where that differs from its order connector --
    mt5_bridge is one provider wearing both roles through two different programs."""
    rel = PROVIDERS[pid].get("market_data_adapter") or (
        PROVIDERS[pid].get("adapter") if "market_data" in PROVIDERS[pid]["roles"] else None)
    return os.path.join(ROOT, rel) if rel else None


def for_role(role, market=None):
    """Provider ids offering `role`, optionally restricted to a market. Registry order, so callers and error
    messages are stable. This is the function that makes 'Data Source != Execution Venue' expressible: asking
    for market_data and asking for execution are two independent questions with two independent answers."""
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}; known: {list(ROLES)}")
    return [pid for pid, p in PROVIDERS.items()
            if role in p["roles"] and (market is None or market in p["markets"])]


def venue_of(pid):
    return PROVIDERS[pid]["venue"]


def status_of(pid):
    return PROVIDERS[pid]["status"]


def is_live(pid):
    """True only for `connected`. A mock_only or not_built provider may never satisfy a live decision
    requirement (CLAUDE.md §6, and SYSTEM-DESIGN.md §6.1's engaged-dimension gate)."""
    return PROVIDERS[pid]["status"] == "connected"


def markets_of(pid):
    return list(PROVIDERS[pid]["markets"])


def alias_of(pid):
    """The short id state files, setup rows and logs use for an execution provider ('futures', 'mt5', 'spot').
    The runner's `venue` field has always been one of these -- it is a PROVIDER selector, not a venue name, and
    naming it here is what lets `venue_of()` stop being a symbol-membership test."""
    return PROVIDERS[pid]["execution_alias"]


def by_source_marker(marker):
    """The provider id that wrote a data file carrying this `_source` marker, or None.

    The marker is the writer's own word, stamped into every OHLCV file. A provider declares a LIST because one
    provider legitimately has several connectors: `binance_public` writes `binance_public_rest_live` from the
    scanner fetch and `binance_public_rest_history` from the paginated history fetch. An entry ending in `*`
    matches by prefix, which is how `yahoo_finance_*` covers one marker per contract code
    (`yahoo_finance_GC=F_research_only` and its siblings).

    The list was a single string until 2026-09-18, and the cost of that was concrete: a scan of `data/live/`
    and `mock/` found two markers, so two were declared -- while `data/history/`, which every backtest reads,
    carried two more. Snapshots of research data came back with `provider: None` until the dataset snapshot
    surfaced it."""
    for pid, p in PROVIDERS.items():
        for declared in p.get("source_markers", ()):
            if declared.endswith("*"):
                if marker.startswith(declared[:-1]):
                    return pid
            elif declared == marker:
                return pid
    return None


def is_research_only(pid):
    """True when a provider supplies a DIFFERENT instrument from the one that gets the order.

    `yahoo_finance` is connected and trustworthy for deep history, and serves front-month futures for symbols
    the system trades as broker CFDs. That is not a staleness problem (`status` is `connected`) and not a mock
    (`is_live` is True) -- it is a third thing, and collapsing it into either would lose the fact that matters:
    a backtest built on it is evidence about futures, not about the traded contract."""
    return bool(PROVIDERS[pid].get("research_only"))


def data_market_type(pid):
    """The market type of the DATA this provider supplies, which is not always the type it executes.

    binance_public serves SPOT klines; binance_futures executes PERPETUAL contracts. A provider carrying both
    roles states the data side in `market_data_market_type` when it differs; mt5_bridge's two roles are the
    same broker CFD series, so it says so explicitly rather than by omission."""
    p = PROVIDERS[pid]
    return p.get("market_data_market_type") or p.get("market_type")


def data_execution_mismatch(market):
    """Does the market's analysed series have a different market type from what it executes? (CLAUDE.md §7)

    Returns None when they agree, else a dict naming both sides. This is not a bug report -- spot and
    perpetual track closely for liquid majors and analysing one while trading the other is a legitimate,
    common choice. It is a PROVENANCE fact that was previously invisible: entry, stop and target levels are
    computed on one instrument's prints and sent to another's order book, and the backtest measures the
    first. §7 exists so that is written down rather than assumed away.
    """
    # Research-only providers are excluded here and handled by research_data_mismatch(). The two questions
    # are disjoint on purpose -- "what does the LIVE analysis read vs what gets the order" and "what does the
    # BACKTEST read vs what gets the order" have different answers for cfd, and a single function reporting
    # {CFD, FUTURES} against {CFD} would say both at once and neither clearly.
    data = [pid for pid in for_role("market_data", market) if is_live(pid) and not is_research_only(pid)]
    execs = [pid for pid in for_role("execution", market) if PROVIDERS[pid]["unattended"]]
    if not data or not execs:
        return None
    d_types = {data_market_type(pid) for pid in data}
    x_types = {market_type_of(pid) for pid in execs}
    if d_types == x_types:
        return None
    return {"market": market, "data_providers": data, "data_market_type": sorted(t for t in d_types if t),
            "execution_providers": execs, "execution_market_type": sorted(x_types)}


def research_data_mismatch(market):
    """Does this market's RESEARCH history come from a different instrument than it executes? (§10)

    The sibling of `data_execution_mismatch()`, and the reason both exist: a backtest is evidence about the
    instrument whose bars it read. For cfd that is front-month futures from `yahoo_finance`, while the venue
    trades broker CFDs -- so `backtested.cfd = ["XAUUSD"]` in instruments.json is a claim about GC=F.

    Returns None when they agree, else a dict naming both sides and the provider's own list of differences.
    Not a defect report: deep history for a related instrument is often the only history there is, and
    `scripts/fetch-history-cfd.py` says so in its docstring. What §10 adds is that a run now RECORDS it.
    """
    research = [pid for pid in for_role("market_data", market) if is_research_only(pid)]
    execs = [pid for pid in for_role("execution", market) if PROVIDERS[pid]["unattended"]]
    if not research or not execs:
        return None
    r_types = {data_market_type(pid) for pid in research}
    x_types = {market_type_of(pid) for pid in execs}
    if r_types == x_types:
        return None
    return {"market": market, "research_providers": research,
            "research_market_type": sorted(t for t in r_types if t),
            "execution_providers": execs, "execution_market_type": sorted(x_types),
            "differences": [d for pid in research
                            for d in PROVIDERS[pid].get("differences_from_traded_instrument", [])]}


def has_capability(pid, capability):
    """Does this provider declare the capability at all (regardless of whether it is connected)?"""
    if capability not in CAPABILITIES:
        raise ValueError(f"unknown capability {capability!r}; known: {sorted(CAPABILITIES)}")
    return capability in PROVIDERS[pid]["capabilities"]


def providers_with(capability, market=None, live_only=False):
    """Provider ids declaring `capability`, optionally restricted to a market and to CONNECTED providers.

    `live_only` is the distinction CLAUDE.md §6 turns on. CoinGlass DECLARES footprint bars and does supply
    them -- as fixtures, with no API key. Asking "can this system read a footprint?" and "can it read one
    right now, for real?" are different questions, and answering the second with the first is precisely how a
    mock satisfies a live decision requirement (SYSTEM-DESIGN.md §6.1 forbids it by name).
    """
    out = []
    for pid, p in PROVIDERS.items():
        if capability not in p["capabilities"]:
            continue
        if market is not None and market not in p["markets"]:
            continue
        if live_only and p["status"] != "connected":
            continue
        out.append(pid)
    return out


def markets_with_capability(capability, live_only=False):
    """Markets in which SOME provider offers the capability. Structural by default, live with `live_only`."""
    out = []
    for pid in providers_with(capability, live_only=live_only):
        for m in PROVIDERS[pid]["markets"]:
            if m not in out:
                out.append(m)
    return out


def capability_report(capability, market):
    """Why a capability is or is not live here, in a form a caller can print or persist.

    CLAUDE.md §6: when a required capability is unavailable, the system must expose the unavailable state AND
    preserve the reason. A bare False loses the reason, and "footprint unavailable" with no cause reads the
    same whether CoinGlass is down, unconfigured, or was never a source for this market at all -- three very
    different things to a person deciding whether to wait.
    """
    declared = providers_with(capability, market)
    live = providers_with(capability, market, live_only=True)
    if live:
        return {"capability": capability, "market": market, "live": True, "providers": live, "reason": None}
    if not declared:
        reason = (f"no provider supplies {capability} for {market} -- it is not a configuration problem, "
                  f"there is no source (docs/architecture/providers.json)")
    else:
        why = ", ".join(f"{pid} is {PROVIDERS[pid]['status']}" for pid in declared)
        reason = f"{capability} for {market} has no CONNECTED provider: {why}"
    return {"capability": capability, "market": market, "live": False, "providers": declared, "reason": reason}


def market_type_of(pid):
    """The canonical market type of a contract on this execution provider (CLAUDE.md §5).

    Ask this, never the venue alias: `alias_of("binance_futures")` is "futures" (Binance's word, kept because
    logs and state rows carry it) while `market_type_of("binance_futures")` is "PERPETUAL" (what the contract
    actually is -- no expiry, funding-paid). Code that reasons about funding, expiry or settlement must use
    the type; code that reads a state row must use the alias."""
    return PROVIDERS[pid]["market_type"]


def unattended_venue_for(market):
    """The execution alias the UNATTENDED pilot uses for this market.

    Two providers can serve one market with different permissions -- crypto has `binance_spot` (manual,
    /execute, one human confirmation per trade) and `binance_futures` (the pilot). `unattended` is what
    separates them, so a provider that requires a human in the loop can never be selected by a loop that has
    no human in it (CLAUDE.md §51). Raises when the answer is not exactly one provider: zero means the market
    cannot be traded unattended and silently returning something would be the fail-open this function exists
    to remove; more than one means a policy choice nobody has made, and guessing it in an order path is the
    kind of silent provider switching CLAUDE.md §6 forbids outright.
    """
    cands = [pid for pid in for_role("execution", market) if PROVIDERS[pid]["unattended"]]
    if len(cands) != 1:
        raise ValueError(
            f"{market!r} has {len(cands)} unattended execution providers ({cands or 'none'}); the pilot needs "
            f"exactly one. Fix docs/architecture/providers.json -- do not let an order path guess.")
    return alias_of(cands[0])


def is_external(pid):
    """True for a third-party dependency; False for this repo's own code declared in a provider role. Only
    external providers' connector paths are owned by the registry to the exclusion of every other module."""
    return PROVIDERS[pid]["external"]


def external_connectors():
    """Basenames of every connector belonging to an EXTERNAL provider -- the set no module outside this reader
    may hard-code (CLAUDE.md §2)."""
    out = set()
    for pid, p in PROVIDERS.items():
        if not p["external"]:
            continue
        for key in ("adapter", "market_data_adapter"):
            if p.get(key):
                out.add(os.path.basename(p[key]))
    return out


if __name__ == "__main__":
    print(f"{'provider':<18}{'venue':<10}{'status':<12}{'markets':<22}roles")
    for pid, p in PROVIDERS.items():
        print(f"{pid:<18}{p['venue']:<10}{p['status']:<12}{','.join(p['markets']):<22}{','.join(p['roles'])}")
    print()
    for role in ROLES:
        print(f"{role:<24}{for_role(role)}")
