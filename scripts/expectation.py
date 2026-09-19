"""THE Expectation record type (CLAUDE.md §17): what a methodology expects, kept apart from what happened.

    import expectation as X
    e = X.create("liquidity_objective", "ict", "draw on BSL 77,728",
                 path=[X.leg("after_entry", 77_083, "target_1"), X.leg("after_entry", 77_728, "target_2")],
                 invalidation=X.invalidation("close below", 76_464, owner="wyckoff"),
                 series=("BTCUSDT", "15m"), event_time="2026-09-17T18:00:00Z")
    e["status"]                       -> "POTENTIAL"
    e2 = X.advance(e, "REACHED", at="2026-09-17T20:00:00Z", because="price traded 77,728")
    e2["original"] == e["original"]   -> TRUE, always. The original is never rewritten.
    X.actual_vs_expected(e2, actual)  -> comparison, computed, never stored back onto the expectation

Why this type exists. §17 asks for something the repo had nothing of: "Expectation is broader than
targetPrice", and what the repo had WAS a target price -- `trade-file.schema.json`'s `targets` is
`{"type": "array", "items": {"type": "number"}}`. Three bare numbers. No methodology, no source evidence, no
creation time, no availableTime, no status, no expected path, no invalidation condition, no provenance: the
eight things §17 says every expectation must preserve, and the file preserved none of them. The lifecycle
vocabulary (POTENTIAL / EXPECTED / CONFIRMED / REACHED / INVALIDATED / CANCELLED / UNKNOWN) appeared nowhere
in the repository -- a grep for it found `status: CANCELLED` on a trade file, an i18n label, and Wyckoff prose.

**Immutability is the point, not a nicety.** §17: "Original expectations are immutable… The actual path must
never rewrite the original expectation." That is what makes §41's failure-learning possible at all: comparing
a thesis against its outcome requires the thesis to still say what it said when it was made. So `create()`
seals the eight required fields into `original`, and `advance()` returns a NEW record whose `original` is the
same frozen mapping -- status lives in a `history` list beside it, never on top of it. `_seal()` refuses to
produce a record whose original is mutable.

**An expectation is not a signal.** Same failure as §12's, one level up: an expectation carrying
`direction: long` has become a trade instruction, and §17 says plainly "Expectations are NOT automatic
signals." The decision-shaped fields are refused outright.

**Independent per methodology.** §17: "Multiple methodologies must maintain independent expectations. Do not
merge their expected paths merely because they appear on the same chart." Enforced two ways: a kind belongs
to exactly one methodology (docs/architecture/methods.json `expectation_kinds`), and `paths_by_methodology()`
returns a mapping rather than a merged list -- there is no function here that concatenates two methodologies'
legs, because the spec forbids the result.
"""
import datetime
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import methods as M
import normalized as N
import pit

# §17's own list, in its own order. UNKNOWN is last because it is the spec's escape hatch, not a stage.
STATES = ("POTENTIAL", "EXPECTED", "CONFIRMED", "REACHED", "INVALIDATED", "CANCELLED", "UNKNOWN")

# Terminal states: an expectation that has reached one is finished and accepts no further transition.
# REACHED/INVALIDATED/CANCELLED are outcomes; the rest are stages on the way.
TERMINAL = ("REACHED", "INVALIDATED", "CANCELLED")

# Which transitions are legal. Written as a table rather than an if-chain because §59 makes this
# version-significant: a change here changes what a historical record could have meant.
#
# UNKNOWN is reachable from any live stage (the spec's "Unknown is a valid state", §9) and can resolve back
# into a stage when the missing information arrives -- it is an absence of knowledge, not an outcome.
TRANSITIONS = {
    "POTENTIAL":   ("EXPECTED", "CONFIRMED", "REACHED", "INVALIDATED", "CANCELLED", "UNKNOWN"),
    "EXPECTED":    ("CONFIRMED", "REACHED", "INVALIDATED", "CANCELLED", "UNKNOWN"),
    "CONFIRMED":   ("REACHED", "INVALIDATED", "CANCELLED", "UNKNOWN"),
    "UNKNOWN":     ("POTENTIAL", "EXPECTED", "CONFIRMED", "REACHED", "INVALIDATED", "CANCELLED"),
    "REACHED":     (),
    "INVALIDATED": (),
    "CANCELLED":   (),
}

# §17's expectation model: the three phases an expected path may describe.
PHASES = ("before_entry", "entry_area", "after_entry")

# The eight things §17 requires EVERY expectation to preserve. Checked by _seal(); a record missing one is
# refused rather than written with a hole in it.
REQUIRED_FIELDS = ("methodology", "source_evidence", "created_at", "available_time",
                   "status", "expected_path", "invalidation", "provenance")

# Fields that would turn an expectation into a trade instruction (§17: "Expectations are NOT automatic
# signals"). Same guard as evidence.FORBIDDEN_FIELDS one rung up the ladder.
FORBIDDEN_FIELDS = ("direction", "side", "signal", "entry", "position_size", "risk_pct",
                    "order", "execute", "verdict", "recommendation")


def kinds(methodology):
    """The expectation kinds this methodology may produce (docs/architecture/methods.json)."""
    return tuple(M.DIMENSIONS[methodology].get("expectation_kinds") or ())


def methodology_of(kind):
    """Which methodology owns this kind -- the check that keeps expectations independent (§17)."""
    for dim in M.ALL_DIMENSIONS:
        if kind in kinds(dim):
            return dim
    return None


def leg(phase, level, label, *, note=None):
    """One step of an expected path. A path is a SEQUENCE of these, which is what makes it a path rather
    than §17's "Do not reduce expectations to target prices"."""
    if phase not in PHASES:
        raise ValueError(f"phase {phase!r} not in {PHASES}")
    out = {"phase": phase, "level": float(level), "label": str(label)}
    if note:
        out["note"] = str(note)
    return out


def invalidation(rule, level, *, owner):
    """The condition that ends this expectation. `owner` is the methodology whose structure defines it --
    the same ownership rule the narrative already enforces (knowledge/integrated/method.md §4.4)."""
    if owner not in M.invalidation_owners():
        raise ValueError(f"invalidation owner {owner!r} must be one of {M.invalidation_owners()}")
    return {"rule": str(rule), "level": float(level), "owner": owner}


def _seal(mapping):
    """Return an immutable view of the original expectation.

    A plain dict would let a later caller edit the thesis after the outcome is known, which is the exact
    failure §17 names. MappingProxyType makes that a TypeError at the point of the attempt rather than a
    silent rewrite discovered during a post-trade review.
    """
    missing = [f for f in REQUIRED_FIELDS if f not in mapping]
    if missing:
        raise ValueError(f"expectation is missing required field(s): {', '.join(missing)} (CLAUDE.md §17)")
    return types.MappingProxyType(dict(mapping))


def create(kind, methodology, statement, *, path, invalidation, source_evidence=None,
           series=None, event_time=None, available_time=None, created_at=None, provenance=None, **extra):
    """One expectation, at birth. Status is always POTENTIAL: §17's lifecycle starts there, and a record
    that could be born CONFIRMED would let a caller skip the evidence that confirms it.

    `available_time` follows §7/§8 -- derived from the source series when one is given, so an expectation
    created from a 15m bar is not knowable before that bar closed. `created_at` is when the analysis ran,
    which is a different fact and is kept separately (§17 requires both).
    """
    for f in FORBIDDEN_FIELDS:
        if f in extra:
            raise ValueError(
                f"{f!r} would make this expectation a trade instruction; CLAUDE.md §17: 'Expectations are "
                f"NOT automatic signals'. Entry/side/size belong to the Trading System (§35), not here.")
    owner = methodology_of(kind)
    if owner is None:
        raise ValueError(f"unknown expectation kind {kind!r}; declared kinds live in "
                         f"docs/architecture/methods.json (dimensions.<m>.expectation_kinds)")
    if owner != methodology:
        raise ValueError(
            f"expectation kind {kind!r} belongs to {owner!r}, not {methodology!r}. CLAUDE.md §17 keeps "
            f"methodologies' expectations independent; borrowing another's vocabulary is how they merge.")
    if not path:
        raise ValueError("an expectation needs an expected_path; §17: 'Do not reduce expectations to "
                         "target prices' -- a path with no legs is a target price with extra steps")
    # Provenance is PASSED IN rather than computed here: N.provenance() needs the loaded series file, and a
    # constructor that reads from disk could not be used on a historical record or in a backtest. The caller
    # that loaded the series has it already (normalized.load -> normalized.provenance).
    avail = available_time
    if avail is None and series and event_time:
        # §7/§8: a bar is knowable one full period after its open, so an expectation drawn from it is too.
        avail = N.available_time({"time": event_time}, series[1]).strftime("%Y-%m-%dT%H:%M:%SZ")
    original = dict(
        kind=kind,
        methodology=methodology,
        statement=str(statement),
        source_evidence=list(source_evidence or []),
        created_at=created_at or _now(),
        event_time=event_time,
        available_time=avail,
        status=STATES[0],
        expected_path=[dict(l) for l in path],
        invalidation=dict(invalidation),
        provenance=provenance,
        series=list(series) if series else None,
        **extra,
    )
    return {"original": _seal(original), "status": STATES[0], "history": (), "id": _ident(original)}


def advance(record, status, *, at=None, because=None):
    """Move an expectation to a new status WITHOUT touching the original.

    Returns a new record. `original` is the same frozen mapping object, so the identity check
    `new["original"] is old["original"]` holds -- the strongest statement available in Python that the
    thesis was not rewritten.
    """
    if status not in STATES:
        raise ValueError(f"status {status!r} not in {STATES}")
    cur = record["status"]
    if status not in TRANSITIONS[cur]:
        raise ValueError(f"{cur} -> {status} is not a legal transition"
                         + (f"; {cur} is terminal" if cur in TERMINAL else ""))
    event = {"from": cur, "to": status, "at": at or _now(), "because": because}
    return {"original": record["original"], "status": status,
            "history": tuple(record["history"]) + (event,), "id": record["id"]}


def is_open(record):
    """Still live -- not yet an outcome. UNKNOWN counts as open: missing information, not a result."""
    return record["status"] not in TERMINAL


def paths_by_methodology(records):
    """Expected paths grouped BY methodology, never merged across them (§17).

    Returns {methodology: [(expectation id, [legs...])]}. Deliberately not a flat list: the spec says "Do
    not merge their expected paths merely because they appear on the same chart", and the shape a function
    returns is what its callers will do.
    """
    out = {}
    for r in records:
        m = r["original"]["methodology"]
        out.setdefault(m, []).append((r["id"], list(r["original"]["expected_path"])))
    return out


def actual_vs_expected(record, actual_path):
    """Compare what happened against the ORIGINAL expectation, returning a fresh comparison.

    Nothing is written back onto the record -- §17: "The actual path must never rewrite the original
    expectation." `actual_path` is a sequence of {"level", "time"} points; a leg counts as met when the
    actual path traded at or through its level, direction taken from the path's own first leg.
    """
    legs = record["original"]["expected_path"]
    levels = [p["level"] for p in actual_path]
    start = levels[0] if levels else None
    met = []
    for l in legs:
        if start is None:
            met.append(None)  # unknown, not False -- an empty actual path is no evidence either way
            continue
        up = l["level"] >= start
        met.append(any((p >= l["level"]) if up else (p <= l["level"]) for p in levels))
    # `reached` is three-valued on purpose. With no actual path there is no evidence either way, and
    # collapsing that to False would let an empty data window read as "the thesis failed" -- which §41 would
    # then cluster as a failure pattern. UNKNOWN stays unknown (§9).
    reached = None if (not met or any(m is None for m in met)) else all(met)
    return {"id": record["id"], "methodology": record["original"]["methodology"],
            "status": record["status"], "legs": [dict(l, met=m) for l, m in zip(legs, met)],
            "reached": reached}


def to_json(record):
    """A JSON-serialisable copy of a record.

    `json.dumps` cannot serialise a MappingProxyType, and the obvious workaround -- making `original` a
    plain dict -- would delete the immutability this whole module exists for. So the conversion lives here,
    once, and callers writing a trade file use it instead of inventing their own.
    """
    return {"id": record["id"], "status": record["status"],
            "original": dict(record["original"]), "history": [dict(h) for h in record["history"]]}


def from_json(blob):
    """Read a record back, re-sealing the original. A record loaded from disk is as immutable as a fresh
    one -- otherwise the guarantee would hold only until the first restart."""
    return {"id": blob["id"], "status": blob["status"],
            "original": _seal(blob["original"]), "history": tuple(dict(h) for h in blob.get("history", ()))}


def as_pit_inputs(records):
    """Expectations as §8 gate inputs -- the spec lists "expectations" among the things PIT applies to."""
    return [pit.input_("expectations",
                       f"{r['original']['methodology']}:{r['original']['kind']}:{r['id']}",
                       r["original"]["available_time"],
                       event_time=r["original"].get("event_time"))
            for r in records if r["original"]["available_time"]]


def admissible(records, decision_time):
    """Which expectations a decision at `decision_time` may use (§8 over §17)."""
    return pit.admit(as_pit_inputs(records), decision_time)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ident(original):
    """A short content id, so a record can be referenced from a trade file without copying it."""
    import hashlib
    key = "|".join(str(original.get(k)) for k in ("kind", "methodology", "statement", "created_at"))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
