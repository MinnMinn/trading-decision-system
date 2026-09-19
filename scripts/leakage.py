"""CLAUDE.md §37 -- proving a backtest is point-in-time correct by attacking it, not by reading it.

§37's rule is one sentence: *"Only information available at the historical decision time may affect the
entry decision. Future market movement may determine stop hit, target hit, MFE, MAE, trade outcome, but may
not influence entry, setup eligibility, methodology interpretation, news filter, risk decision, confluence,
expectation creation."*

A code review cannot establish that. An experiment can:

    1. Run the engine over a real series and record every decision it makes.
    2. REPLACE every bar strictly after a cut with something wildly different -- same length, same
       timestamps, same field names, different prices.
    3. Run it again.

Every decision whose entry happened at or before the cut must come back **byte-identical**. If any of them
moves, the engine read a bar that had not happened yet. Outcome fields (`outcome`, `R`, `exit`, `exit_time`)
are expected to move and are excluded -- §37 explicitly allows future movement to decide those.

Three mutation modes run by default, because a single one can agree with the original by accident:
`scale` (×3 away), `freeze` (a flat line at the cut's close) and `invert` (mirrored around the cut's close).
A leak that survives all three is not a coincidence.

    import leakage
    rep = leakage.probe(run, candles, cut, key=..., decision_fields=...)
    rep["ok"] -> True when nothing moved; rep["violations"] names what did.

This module only *detects*. What a research run does about a detection is §38's question.
"""
import copy

MODES = ("scale", "freeze", "invert")

# Fields a backtest trade record carries that §37 says the future is ALLOWED to determine. Anything not in
# here is a decision field and must be reproducible from the past alone.
OUTCOME_FIELDS = ("outcome", "R", "exit", "exit_time", "mfe", "mae")


def index_of_time(candles, t):
    """Index of the bar with this timestamp, or None. Linear on purpose: the series are small enough and a
    dict would have to be rebuilt per mutation anyway."""
    for i, c in enumerate(candles):
        if c["time"] == t:
            return i
    return None


def mutate_future(candles, cut, mode="scale", factor=3.0):
    """A copy of `candles` in which every bar strictly after index `cut` is replaced.

    Length, order, timestamps and field names are preserved, so the engine's loop bounds, pivot windows and
    horizon arithmetic are all unchanged -- the ONLY thing that differs is the price information the future
    carries. Truncating instead would change `len(candles)` and therefore which setups are scanned at all,
    which would make a difference in the output mean nothing.
    """
    if mode not in MODES:
        raise ValueError(f"unknown mutation mode {mode!r}; implemented: {list(MODES)}")
    out = copy.deepcopy(candles)
    if cut >= len(out) - 1:
        return out
    anchor = float(out[cut]["close"])
    for i in range(cut + 1, len(out)):
        bar = out[i]
        if mode == "freeze":
            o = h = l = c = anchor
        elif mode == "scale":
            o, h, l, c = (anchor + (float(bar[k]) - anchor) * factor for k in ("open", "high", "low", "close"))
        else:                                    # invert: mirror the move around the cut's close
            o, h, l, c = (anchor - (float(bar[k]) - anchor) for k in ("open", "high", "low", "close"))
            h, l = max(o, h, l, c), min(o, h, l, c)
        # A bar must still be a bar: §20's own validity rule is low <= open/close <= high, and feeding the
        # engine an impossible candle would make it refuse for a reason that has nothing to do with leakage.
        bar["open"], bar["close"] = o, c
        bar["high"], bar["low"] = max(o, h, l, c), min(o, h, l, c)
    return out


def probe(run, candles, cut, *, key, decision_fields, modes=MODES, entry_time_field="entry_time"):
    """Run the engine on the real series and on each mutated future; report what moved.

    `run(candles)`        -> iterable of records (a backtest's trades).
    `key(record)`         -> a stable identity for one decision.
    `decision_fields`     -> the fields §37 forbids the future to influence.
    `entry_time_field`    -> which field says WHEN the decision was acted on; records whose entry falls after
                             the cut are excluded, because those were legitimately decided on mutated bars.

    Returns {"ok", "cut", "checked", "modes", "violations": [{mode, key, field, before, after}]}.
    A record that DISAPPEARS under mutation is a violation with field "__present__".
    """
    baseline = {}
    for rec in run(candles):
        i = index_of_time(candles, rec[entry_time_field])
        if i is not None and i <= cut:
            baseline[key(rec)] = rec

    violations = []
    for mode in modes:
        mutated = mutate_future(candles, cut, mode)
        seen = {key(r): r for r in run(mutated)}
        for k, before in baseline.items():
            after = seen.get(k)
            if after is None:
                violations.append({"mode": mode, "key": k, "field": "__present__",
                                   "before": "decided", "after": "gone"})
                continue
            for f in decision_fields:
                if before.get(f) != after.get(f):
                    violations.append({"mode": mode, "key": k, "field": f,
                                       "before": before.get(f), "after": after.get(f)})
    return {"ok": not violations, "cut": cut, "checked": len(baseline), "modes": list(modes),
            "violations": violations}


def describe(report):
    """One line for a research report or a CI log."""
    if report["ok"]:
        return (f"PIT OK: {report['checked']} decisions at or before the cut are unchanged under "
                f"{len(report['modes'])} mutations of the future ({', '.join(report['modes'])})")
    first = report["violations"][0]
    return (f"LOOK-AHEAD: {len(report['violations'])} decision field(s) moved when the future changed, e.g. "
            f"{first['key']} {first['field']}: {first['before']!r} -> {first['after']!r} under "
            f"'{first['mode']}'. CLAUDE.md §37: future movement may determine the OUTCOME and nothing else.")
