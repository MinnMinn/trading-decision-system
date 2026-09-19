"""CLAUDE.md §20 -- the six data-quality states, computed, and the gate that acts on them.

    import quality as Q
    Q.assess(series, "15m", symbol="BTCUSDT")   -> ("FRESH"|"STALE"|"PARTIAL"|..., reason)
    Q.gate({"candles": "PARTIAL"}, required=("candles",))   -> ("BLOCK_ENTRY", why)

§7 already produces a quality word per series, and this module does not replace it: `normalized.QUALITY` is
`AVAILABLE / STALE / MOCK / UNAVAILABLE`, which answers "can I use this feed at all". §20 asks a different
and finer question -- `FRESH / STALE / MISSING / PARTIAL / INVALID / UNKNOWN` -- and three of those six were
**unrepresentable**:

  * **PARTIAL** -- a series with holes in it and a complete one produced the same word. A gapped window
    silently became a whole one, which is the "STALE → FRESH" conversion §20 forbids wearing a different hat:
    an indicator computed over a window with bars missing is not a degraded indicator, it is a different one.
  * **INVALID** -- nothing checked that a candle's high was its highest, that times ascended, or that bars
    were not duplicated. Corrupt provider data read as AVAILABLE.
  * **UNKNOWN** -- there was no way to say "I cannot tell", so every uncertainty collapsed into a confident
    word. §9: "Unknown is a valid state."

And §20's second half had nothing at all: *"Critical required inputs that do not satisfy their configured
quality requirement must prevent unsafe decision-making"*, with outcomes WAIT / NO TRADE / BLOCK ENTRY /
UNKNOWN / HUMAN CONFIRMATION. The block was narrated by a model in `/analyze` prose, never computed.

**The conversions §20 names are refused, not avoided by convention.** `coerce()` exists only to raise: there
is one place in the codebase where turning UNKNOWN into a lesser state is spelled, and it is a function whose
entire body is an exception. That is deliberate -- a rule with no code attached is a rule that erodes.

**How PARTIAL is computed, and why not by counting bars.** The obvious test is "did we get as many bars as we
asked for", with `automation.SCAN_WINDOW[tf]["bars"]` as the expected number. Measured against the live files,
that test is wrong: ASTERUSDT's 1W series holds 50 bars against a window of 240, and it is COMPLETE -- the coin
is a year old. A count check would mark six young instruments PARTIAL forever and teach a reader to ignore the
state. So PARTIAL is computed from CONTINUITY instead -- missing bars inside the series' own range, which is a
fact about the data rather than about the instrument's age -- and only for markets whose tape has no scheduled
closures (`instruments.is_continuous`). All 45 live crypto files are gapless; every XAUUSD/XAGUSD file has gaps
and every one is a weekend. For a non-continuous market the question is genuinely unanswerable here, so it is
left unanswered rather than guessed in either direction. `expected_bars` remains available for the caller that
really does know its window -- a backtest that requested N bars from a fixed range.
"""
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import instruments as I
import normalized as N

# §20's own list, in its own order.
STATES = ("FRESH", "STALE", "MISSING", "PARTIAL", "INVALID", "UNKNOWN")

# §20's own list of what a failing required input may produce.
DECISIONS = ("WAIT", "NO_TRADE", "BLOCK_ENTRY", "UNKNOWN", "HUMAN_CONFIRMATION")

# Which states are good enough to decide on, by default. Everything else must be configured explicitly or it
# gates -- the safe direction, since §1 puts Safety above Convenience.
USABLE = ("FRESH",)

# What a failing required input produces, by state. §20 lists the outcomes but not the mapping, so this is
# this project's choice and is stated as such:
#   PARTIAL/INVALID -> BLOCK_ENTRY : the data is wrong, and waiting will not make a truncated window whole
#   STALE           -> WAIT        : the feed works, the bar is late; waiting is exactly the right response
#   MISSING         -> NO_TRADE    : nothing to wait for
#   UNKNOWN         -> HUMAN_CONFIRMATION : §20 forbids guessing, and a person can look
DEFAULT_ACTION = {
    "FRESH": None,
    "STALE": "WAIT",
    "MISSING": "NO_TRADE",
    "PARTIAL": "BLOCK_ENTRY",
    "INVALID": "BLOCK_ENTRY",
    "UNKNOWN": "HUMAN_CONFIRMATION",
}

# A fetch this far below its requested window is PARTIAL rather than merely short. Not 100%: a live feed's
# most recent bar legitimately has not closed yet, and calling that PARTIAL would gate every tick.
PARTIAL_BELOW = 0.98


def assess(series, timeframe, *, symbol=None, continuous=None, expected_bars=None, now=None):
    """The §20 state of one series, with the reason that produced it.

    `series` is the loaded file (normalized.load) or None when there is nothing to load. `symbol` resolves
    `continuous` from the registry; pass `continuous` directly when there is no symbol (a fixture, a
    hand-built series in a test). When neither is given the continuity check is skipped rather than assumed.

    Order matters: a file that is absent cannot be invalid, and one that is invalid should not be reported as
    merely incomplete.
    """
    if series is None:
        return "MISSING", "no series file for this symbol/timeframe"

    candles = series.get("candles")
    if candles is None:
        return "INVALID", "series has no `candles` key at all"
    if not isinstance(candles, list):
        return "INVALID", f"`candles` is {type(candles).__name__}, not a list"
    if not candles:
        return "MISSING", "series carries zero candles"

    bad = _structural_fault(candles)
    if bad:
        return "INVALID", bad

    if continuous is None and symbol is not None:
        continuous = I.is_continuous(symbol)
    if continuous:
        hole = _first_hole(candles, timeframe)
        if hole:
            return "PARTIAL", hole

    if expected_bars:
        have = len(candles)
        if have < expected_bars * PARTIAL_BELOW:
            return "PARTIAL", (f"{have} of {expected_bars} bars ({have / expected_bars:.0%}); an indicator "
                               f"computed over this window is not a degraded one, it is a different one")

    # The same fact under two names. A raw file on disk calls it `last_updated`; `normalized.load()` lifts it
    # into `provenance.received_time` (§7's vocabulary) and does not leave a copy at the top level. Reading
    # only the first spelling made the DOCUMENTED call path -- assess(normalized.load(...)) -- return UNKNOWN
    # for a perfectly fresh series, and a required input then gated on HUMAN_CONFIRMATION. Found 2026-09-18 by
    # running the real call rather than the one the tests happened to use (they fed the raw dict).
    received = series.get("last_updated") or (series.get("provenance") or {}).get("received_time")
    if not received:
        return "UNKNOWN", ("series carries no `last_updated`, so its freshness cannot be determined; "
                           "CLAUDE.md §20 forbids treating that as FRESH")
    try:
        received_dt = _parse(received)
    except Exception as exc:
        return "INVALID", f"`last_updated` {received!r} is not a timestamp ({exc})"

    now = now or datetime.datetime.now(datetime.timezone.utc)
    age = (now - received_dt).total_seconds()
    if age > N.STALE_AFTER_BARS * N.tf_seconds(timeframe):
        return "STALE", (f"last updated {age / 60:.0f} min ago, more than "
                         f"{N.STALE_AFTER_BARS} x {timeframe}")

    # A fixture that is complete and freshly written is genuinely FRESH -- but liveness is CLAUDE.md §6's
    # question, not §20's, and a caller reading only the state would never learn it. Say so in the reason.
    fixture = " (FIXTURE -- §6 live-sourcing is a separate question this state does not answer)" \
        if series.get("_mock") else ""
    return "FRESH", f"{len(candles)} bars, updated {max(age, 0) / 60:.0f} min ago{fixture}"


def _first_hole(candles, timeframe):
    """The first missing stretch inside a continuous series, or None. Only meaningful for a 24/7 tape."""
    step = N.tf_seconds(timeframe)
    for i in range(1, len(candles)):
        gap = (_parse(candles[i]["time"]) - _parse(candles[i - 1]["time"])).total_seconds()
        if gap > step:
            return (f"{int(gap / step) - 1} bar(s) missing between {candles[i - 1]['time']} and "
                    f"{candles[i]['time']} on a market that never closes; the window has holes, so an "
                    f"indicator computed over it is not a degraded one, it is a different one")
    return None


def _structural_fault(candles):
    """The faults that make a series INVALID rather than merely incomplete. First one wins -- a reader acts
    on the first reason, and listing all of them would not change the verdict."""
    prev_t = None
    for i, c in enumerate(candles):
        for f in ("time", "open", "high", "low", "close"):
            if f not in c:
                return f"candle {i} has no {f!r}"
        try:
            o, h, l, cl = float(c["open"]), float(c["high"]), float(c["low"]), float(c["close"])
        except (TypeError, ValueError):
            return f"candle {i} has non-numeric OHLC"
        if h < l:
            return f"candle {i} at {c['time']}: high {h} is below low {l}"
        if not (l <= o <= h and l <= cl <= h):
            return f"candle {i} at {c['time']}: open/close outside the high-low range"
        try:
            t = _parse(c["time"])
        except Exception:
            return f"candle {i} time {c['time']!r} is not a timestamp"
        if prev_t is not None:
            if t == prev_t:
                return f"candle {i} repeats timestamp {c['time']}"
            if t < prev_t:
                return f"candle {i} at {c['time']} goes backwards in time"
        prev_t = t
    return None


def usable(state, *, allow=USABLE):
    """Is this state good enough to decide on? Configurable per §20's 'quality requirements may differ by
    data type, methodology, setup, Trading System, timeframe, market type, account, mode'."""
    if state not in STATES:
        raise ValueError(f"unknown quality state {state!r}; §20 enumerates {list(STATES)}")
    return state in allow


def gate(states, *, required, allow=USABLE, action=None):
    """§20's second half: what a failing REQUIRED input does to the decision.

    `states` maps input name -> §20 state. `required` names the inputs the active Trading System declared
    REQUIRED_FOR_DECISION (§35); anything else may be degraded without gating, which is §62's whole point.

    Returns (decision, reasons). `decision` is None when every required input is usable.
    """
    action = {**DEFAULT_ACTION, **(action or {})}
    reasons, decisions = [], []
    for name in required:
        state = states.get(name, "MISSING")
        if usable(state, allow=allow):
            continue
        act = action.get(state) or "BLOCK_ENTRY"
        decisions.append(act)
        reasons.append(f"required input {name!r} is {state} -> {act}")
    if not decisions:
        return None, []
    # Most restrictive wins: a run that would BLOCK_ENTRY on one input must not merely WAIT because another
    # input was only late. §1 puts Safety first and this is where that ordering becomes an expression.
    order = ("BLOCK_ENTRY", "NO_TRADE", "HUMAN_CONFIRMATION", "WAIT", "UNKNOWN")
    return min(decisions, key=order.index), reasons


def coerce(state, to):
    """The conversions §20 forbids, in the one place they are spelled -- so that spelling them raises.

    §20: "Never silently convert UNKNOWN -> LOW, MISSING -> EMPTY, STALE -> FRESH." A prohibition with no
    code attached is a prohibition that erodes; this function exists so that the erosion has to be deliberate
    enough to delete a raise.
    """
    raise ValueError(
        f"refusing to convert {state} -> {to}. CLAUDE.md §20: 'Never silently convert UNKNOWN -> LOW, "
        f"MISSING -> EMPTY, STALE -> FRESH.' If the state is wrong, fix what produced it; if a caller needs "
        f"to proceed anyway, that is a configured allow-list (quality.gate(allow=...)), not a relabelling.")


def from_normalized(word):
    """Translate §7's four-word feed vocabulary into §20's six-state one, where that is possible.

    MOCK deliberately has no §20 state: 'is this a fixture' is a PROVENANCE question (§7), not a quality one
    -- a mock series can be perfectly fresh and complete and still must not satisfy a live requirement (§6).
    Conflating the two is how a fixture ends up scoring. Returns None to force the caller to ask §6 instead.
    """
    return {"AVAILABLE": "FRESH", "STALE": "STALE", "UNAVAILABLE": "MISSING", "MOCK": None}.get(word)


def _parse(value):
    if isinstance(value, datetime.datetime):
        return value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)
    return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
