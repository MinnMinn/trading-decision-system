"""THE point-in-time gate (CLAUDE.md §8): one place that answers "was this knowable yet?".

    import pit
    pit.admit([pit.input_("candles", "BTCUSDT 15m", available_time=t_close)], decision_time=now)
    -> {"ok": True, "admitted": [...], "refused": []}

§8's invariant is one line -- `availableTime <= decisionTime` -- and it applies to sixteen kinds of input,
from candles to news revisions to a provider's later correction of a figure it already published. This repo
enforced it for exactly one of those kinds, candles, in three different places and three different ways:

  * `scripts/live_rules.py` `read_at()` -- by INDEX: may read candles[:i+1] and nothing later.
  * `scripts/strategy-runner.py` `drop_forming()` -- by TIME: drop a bar whose period has not elapsed.
  * `scripts/ict-scan.py` -- by POSITION: verdicts use the last completed bar `c[-2]`, and the forming bar
    `c[-1]` is reported separately and may never confirm a break (`ict-scan.py:241`).

Three correct mechanisms answering one question in three vocabularies. That is survivable for candles, which
all three were written for; it does not extend. News has no bar index, a provider correction has no position
in a series, and an expectation's creation time is not a candle boundary -- so when those arrive there is
nothing for them to reuse, and the likely outcome is a fourth mechanism, or none.

So this module states the invariant once, over an input's `available_time`, in a form any of the sixteen kinds
can present. It does NOT replace the three above: each is doing extra work in its own domain (window shape,
bar dropping, reference selection) and rewriting the live order path to funnel through a new abstraction would
be a large change to earn a small one. What it does is give the invariant a single definition that the new
kinds can use, and `scripts/tests/test_pit.py` proves the existing mechanisms agree with it on the one
question they share.

**Boundary convention:** `available_time == decision_time` is ADMISSIBLE. A bar that closes exactly at the
decision instant was available at it; `drop_forming()` has always drawn the line this way (it drops only when
`available > now`), and disagreeing here would silently change which bars a live setup sees.
"""
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

# The sixteen kinds CLAUDE.md §8 enumerates, as snake_case ids. Declared here so a new input type has to be
# named before it can be gated, and so scripts/tests/test_pit.py can check this list against the spec's own
# bullets -- if §8 grows a seventeenth kind, the test fails rather than the kind going ungated.
#
# Several have no producer in this repo yet (news, economic_calendar, expectations, provider_corrections,
# revisions, classification_changes, trades, order_book). They are listed anyway: CLAUDE.md §28 warns that the
# moment a calendar joins the backtest it leaks by construction, and a kind that is already named and already
# gated is a kind that cannot quietly arrive without a PIT story.
INPUT_KINDS = (
    "candles",
    "trades",
    "order_book",
    "open_interest",
    "funding",
    "liquidations",
    "footprint",
    "heatmap",
    "derived_analytics",
    "methodology_analysis",
    "expectations",
    "news",
    "economic_calendar",
    "provider_corrections",
    "revisions",
    "classification_changes",
)


def _aware(t):
    """Accept an ISO-8601 Z string or a datetime; return an aware UTC datetime.

    Naive datetimes are REFUSED rather than assumed to be UTC. A naive timestamp in a point-in-time check is
    an unanswered question about which clock it came from, and guessing is how a DST-shifted local time reads
    as an hour of free look-ahead."""
    if isinstance(t, str):
        t = datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))
    if not isinstance(t, datetime.datetime):
        raise TypeError(f"expected a datetime or ISO-8601 string, got {type(t).__name__}")
    if t.tzinfo is None:
        raise ValueError(f"naive timestamp {t!r} in a point-in-time check: name the timezone. A naive time is "
                         f"an unanswered question about which clock it came from (CLAUDE.md §8).")
    return t.astimezone(datetime.timezone.utc)


def input_(kind, identifier, available_time, event_time=None, source=None):
    """One gated input. `available_time` is when it became knowable -- not when it happened.

    The distinction is the whole point and §7 keeps the two fields apart for it: a 15m bar opening at 18:00
    HAPPENED at 18:00 and became knowable at 18:15, and an economic figure released at 13:30 for a reference
    month of January became knowable at 13:30, not in January."""
    if kind not in INPUT_KINDS:
        raise ValueError(f"unknown input kind {kind!r}; CLAUDE.md §8 enumerates {list(INPUT_KINDS)}")
    return {"kind": kind, "id": identifier, "available_time": _aware(available_time),
            "event_time": _aware(event_time) if event_time is not None else None,
            "source": source}


def admit(inputs, decision_time):
    """Partition inputs into those a decision at `decision_time` may use and those it may not.

    Returns the refusals WITH reasons rather than a bare boolean. A gate that answers only "no" leaves the
    caller unable to say whether to wait (the input is late) or to give up (the input is from the future and
    something is wrong upstream), and CLAUDE.md §6/§20 both require the reason to survive.
    """
    dt = _aware(decision_time)
    admitted, refused = [], []
    for item in inputs:
        at = item["available_time"]
        if at <= dt:
            admitted.append(item)
        else:
            refused.append(dict(item, reason=(
                f"{item['kind']} {item['id']!r} becomes available at {at.isoformat()}, after the decision time "
                f"{dt.isoformat()} -- using it would be look-ahead of "
                f"{(at - dt).total_seconds():.0f}s (CLAUDE.md §8)")))
    return {"ok": not refused, "decision_time": dt, "admitted": admitted, "refused": refused}


def assert_admissible(inputs, decision_time):
    """Raise on any future-dated input. For call sites where continuing would produce an invalid result rather
    than a degraded one -- a backtest bar, a research run -- failing loudly beats returning something."""
    r = admit(inputs, decision_time)
    if not r["ok"]:
        raise LookAheadError("; ".join(x["reason"] for x in r["refused"]))
    return r


class LookAheadError(AssertionError):
    """Raised when a decision would use information that did not exist yet. An AssertionError subclass on
    purpose: this is an invariant violation, not a recoverable condition."""


def candle_input(candle, timeframe, symbol=None):
    """A candle as a gated input, using the one definition of when a bar becomes knowable (§7)."""
    import normalized as N
    return input_("candles", f"{symbol or '?'} {timeframe} @ {candle['time']}",
                  available_time=N.available_time(candle, timeframe),
                  event_time=candle["time"])


def series_as_of(candles, timeframe, decision_time, symbol=None):
    """The prefix of `candles` a decision at `decision_time` may read.

    This is `drop_forming()` generalized from "drop the last bar if it is still forming" to "keep every bar
    that was knowable" -- which is the same thing for a well-formed trailing series, and not the same thing
    for a series containing a gap, a duplicate or a future-stamped row. CLAUDE.md §55 asks for exactly those
    adversarial cases; this returns the honest answer for all of them instead of trusting the last row."""
    import normalized as N
    dt = _aware(decision_time)
    return [c for c in candles if N.available_time(c, timeframe) <= dt]
