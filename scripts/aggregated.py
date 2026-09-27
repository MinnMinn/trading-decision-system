"""CLAUDE.md §23 -- aggregated intelligence keeps its scope, and cannot be presented as one venue's figure.

    import aggregated as A
    rec = A.load("mock/coinglass/open-interest.BTCUSDT.json")   # the five §23 fields, joined from the registry
    A.describe(rec, "open interest")   -> 'Aggregated open interest across venues (venues UNDECLARED) ...'
    A.attribute(rec, venue="okx")      -> raises

§23 is short and has two halves:

    "Aggregated intelligence such as CoinGlass must preserve: aggregation scope, underlying venues, timestamp,
     provider, source identifier. Never present aggregated information as if it came from one venue.
     For example: 'Aggregated OI across venues' must not become 'OKX OI' unless the source is actually OKX."

**The preserving half is already done and this module does not redo it.** `providers.json` declares
`aggregation_scopes`, and `coinglass` carries `aggregation_scope: multi_venue` with
`underlying_venues: ["UNDECLARED"]` and a note explaining why naming an unverified venue set would be the same
error in the other direction. `normalized.provenance()` emits both fields on every series. What was missing is
that the aggregated FILES could not reach any of it: `mock/coinglass/*.json` carried no `_source` marker, so
nothing could say which provider wrote them, and §23's five fields could not be attached to a figure even in
principle. That marker now exists and `load()` does the join.

**The presenting half did not exist at all.** The rule lived as prose in a registry note -- the shape a rule
takes just before it stops being applied. `attribute()` is that rule with code attached: asking for a
single-venue label on a multi_venue record raises, and `describe()` produces the phrasing §23's own example
asks for. There is one place in this repo where a cross-venue figure can be given a venue's name, and it is a
function that refuses.

**Why a `venue` argument exists at all, rather than no such function.** Because the legitimate case is real: a
single_venue provider's open interest genuinely IS Binance's, and saying so is not a violation. A guard that
made attribution impossible would be routed around. `attribute()` permits exactly the case the registry says
is true and refuses the one §23 names.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from repo_paths import repo_rel
import providers as P

# §23's own list, in its own order.
REQUIRED_FIELDS = ("aggregation_scope", "underlying_venues", "timestamp", "provider", "source_identifier")

# The value `underlying_venues` carries when the vendor has not told us which venues it aggregates. It is a
# real answer, not a missing one: §9's "Unknown is a valid state", and naming a venue set nobody verified would
# be the same fabrication §23 forbids, pointed the other way.
UNDECLARED = "UNDECLARED"


def load(path, symbol=None):
    """One aggregated-intelligence file -> a record carrying §23's five fields.

    The scope and the venue list are NOT read from the file: they are facts about the PROVIDER, and
    `providers.json` owns them (the same reasoning `normalized.py` gives for not copying fifteen fields into a
    hundred data files). The file's `_source` marker is what names the provider; a file without one is refused
    rather than guessed, because guessing the provider guesses the aggregation scope with it.
    """
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    marker = raw.get("_source")
    if not marker:
        raise ValueError(
            f"{repo_rel(path, ROOT)} carries no `_source` marker, so the provider that wrote it cannot "
            f"be identified -- and with it neither can its aggregation scope. CLAUDE.md §23 requires an "
            f"aggregate to preserve its scope and underlying venues; a file that cannot name its provider "
            f"cannot preserve either, and defaulting to single_venue would be exactly the misattribution §23 "
            f"forbids.")
    provider = P.by_source_marker(marker)
    if provider is None:
        raise ValueError(f"{repo_rel(path, ROOT)} declares `_source: {marker!r}`, which no provider in "
                         f"docs/architecture/providers.json claims. Add it to that provider's "
                         f"`source_markers` rather than teaching this reader a second spelling.")
    p = P.provider(provider)
    return {
        "provider": provider,
        "aggregation_scope": p["aggregation_scope"],
        "underlying_venues": list(p["underlying_venues"]),
        "timestamp": raw.get("last_updated") or raw.get("snapshot_time"),
        "source_identifier": repo_rel(path, ROOT),
        "symbol": symbol or raw.get("symbol"),
        "is_mock": bool(raw.get("_mock")),
        "payload": raw,
    }


def is_aggregate(record):
    return record["aggregation_scope"] == "multi_venue"


def attribute(record, venue):
    """Name the venue a figure came from -- or refuse, when it did not come from one.

    §23's own example: "Aggregated OI across venues" must not become "OKX OI" unless the source is actually OKX.
    """
    declared = [v for v in record["underlying_venues"] if v != UNDECLARED]
    if is_aggregate(record) and len(declared) != 1:
        raise ValueError(
            f"refusing to attribute {record['provider']}'s figure to venue {venue!r}: its aggregation_scope is "
            f"{record['aggregation_scope']} across {record['underlying_venues']}. CLAUDE.md §23: 'Never "
            f"present aggregated information as if it came from one venue' -- 'Aggregated OI across venues' "
            f"must not become '{venue.upper()} OI' unless the source is actually {venue.upper()}. Use "
            f"aggregated.describe() for the honest phrasing.")
    if declared and venue.lower() not in [v.lower() for v in declared]:
        raise ValueError(
            f"refusing to attribute {record['provider']}'s figure to venue {venue!r}: the registry says it "
            f"comes from {declared}. A figure may only be labelled with the venue it actually came from.")
    return venue


def describe(record, what):
    """The phrasing §23's example asks for -- said the same way every time, from the registry.

    A multi-venue figure says it is aggregated AND says over what; where the venue set is undeclared it says
    that too, rather than leaving a reader to assume it was checked.
    """
    venues = [v for v in record["underlying_venues"] if v != UNDECLARED]
    if is_aggregate(record):
        over = ", ".join(venues) if venues else f"venues {UNDECLARED}"
        return f"Aggregated {what} across venues ({over}) — {record['provider']}"
    if len(venues) == 1:
        return f"{venues[0]} {what} — {record['provider']}"
    return f"{what} — {record['provider']} (scope: {record['aggregation_scope']})"


def check(record):
    """Reasons this record violates §23, or [] if it is conformant. The shape §12/§18's checkers use."""
    problems = []
    for f in REQUIRED_FIELDS:
        if record.get(f) in (None, ""):
            problems.append(f"aggregated record preserves no {f!r} (CLAUDE.md §23 lists it as required)")
    if record.get("aggregation_scope") not in P.AGGREGATION_SCOPES:
        problems.append(f"aggregation_scope {record.get('aggregation_scope')!r} is not one the registry "
                        f"declares: {sorted(P.AGGREGATION_SCOPES)}")
    if is_aggregate(record) and not record.get("underlying_venues"):
        problems.append("a multi_venue aggregate names no underlying venues at all -- not even UNDECLARED, "
                        "which is the honest answer when the vendor has not said")
    return problems
