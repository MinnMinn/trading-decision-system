"""CLAUDE.md §24-§32 -- Event Risk: first-class, point-in-time, per-instrument, and fail-CLOSED.

    import event_risk as ER
    ER.state("BTCUSDT", at="2026-09-18T17:55:00Z")      -> ('BLOCKED', 'FOMC ... pre-window', [...])
    ER.blocked("BTCUSDT", at=..., decision_time=...)     -> (True, reason)
    ER.windows("BTCUSDT", decision_time=...)             -> merged restricted windows

Nine sections land here because they are one subsystem, and splitting them across nine modules would
scatter one decision. What each contributes:

  §24 Event Risk is a GATE, never a methodology, never a confluence dimension. Default 10 minutes before
      and 10 after a HIGH-impact release -- and configurable, which is why both numbers live in
      `event-calendar.json policy` rather than in this file.
  §25 HIGH / MEDIUM / LOW / UNKNOWN, with HIGH restricted by default, MEDIUM configurable, and **UNKNOWN
      never silently treated as LOW**. STRICT mode may turn UNKNOWN into NO TRADE.
  §26 Relevance: an event reaches an instrument through a declared currency, country or asset class --
      never "every event applies to everything".
  §27 `scheduled_event_time` and `actual_release_time` are different fields and stay different. Before the
      event the schedule is used; after it the actual is preferred where known; and a later-learned actual
      time can never move a window that an earlier decision was judged against.
  §28 Point-in-time: an event is visible to a decision only when `available_time <= decision_time`. A
      revision published after the decision does not exist as far as that decision is concerned.
  §29 The calendar carries a snapshot id / version / `covers_through`, so a historical evaluation can say
      WHICH calendar state it saw, and so a stale file becomes UNKNOWN rather than silence.
  §30 Windows are deterministic and OVERLAPPING EVENTS PRODUCE THE UNION. Adjacent windows merge. This is
      where the old implementation had a demonstrated hole.
  §31 Restrictions apply to NEW ENTRY. What happens to an open position is separate configuration and
      defaults to HOLD -- nothing closes itself because a release is approaching.
  §32 Fail-safe: missing / stale / invalid / unknown calendar applies the CONFIGURED outcome, default
      BLOCK_ENTRY. Never "no news".

**What was there before, and why this is a rewrite rather than a patch.** `strategy-runner.event_blackout`
ran a regex for `YYYY-MM-DD HH:MM` over the ENTIRE TEXT of `event-calendar.md` and blocked if any match was
within +/-30 minutes. Three consequences, all live on the order path:

  * The file's own **"How to add an entry" example** was a match, so a documentation line acted as a real
    blackout window.
  * A row written as `17:00Z - 20:00Z` parsed as two POINT events, leaving **17:30-19:30 unprotected** --
    a three-hour FOMC window with a two-hour hole in the middle of it.
  * Every failure -- file absent, unreadable, empty, malformed -- returned `None`, which the caller reads
    as "no news". §32's exact prohibition, applied to the code that places orders.

None of that is fixable by adjusting the regex, because the input was never a data format.
"""
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import pit  # noqa: E402  -- CLAUDE.md §8 has ONE reader and this is it
import instruments as I

PATH = os.path.join(ROOT, "docs", "architecture", "event-calendar.json")

IMPACTS = ("HIGH", "MEDIUM", "LOW", "UNKNOWN")
STATUSES = ("scheduled", "released", "revised", "cancelled")
POSITION_ACTIONS = ("HOLD", "REDUCE_RISK", "CLOSE_BEFORE_NEWS", "CUSTOM")
FAIL_SAFE_ACTIONS = ("BLOCK_ENTRY", "UNKNOWN", "HUMAN_CONFIRMATION")

# What `state()` can answer. CLEAR is the only one that permits a new entry.
CLEAR, BLOCKED, UNAVAILABLE = "CLEAR", "BLOCKED", "UNAVAILABLE"


class CalendarUnavailable(Exception):
    """The calendar could not be used: absent, unreadable, malformed, or stale (§32).

    Carries the CONFIGURED fail-safe action rather than a bare failure, because §32's requirement is not
    "fail" -- it is "apply the configured fail-safe behaviour", and a caller that cannot see which one was
    configured cannot apply it.
    """

    def __init__(self, reason, action="BLOCK_ENTRY"):
        super().__init__(reason)
        self.reason = reason
        self.action = action


def _parse(ts):
    """§8's timestamp rule, from §8's own reader.

    This used to assume UTC for a naive datetime and hand back a naive one for a string with no zone, which
    diverged from `pit._aware()` in the one case that matters: with BOTH sides naive, `visible()` returned a
    boolean computed in an unnamed clock -- a point-in-time answer with no clock behind it -- and with one side
    aware it raised a bare TypeError instead of a §8 refusal with a reason. Two implementations of one
    invariant is what CLAUDE.md §58 means by "duplicated domain rules"; found 2026-09-18 by the final
    full-system pass, which compared the two rather than reading either.
    """
    return pit._aware(ts)


def load(path=None, at=None):
    """The calendar, or CalendarUnavailable carrying the configured fail-safe (§32).

    `at` is the wall-clock the staleness check is made against. A calendar whose `covers_through` has passed
    is STALE: it is not wrong, it simply stops making a claim, and §32 lists stale beside missing.
    """
    p = path or PATH
    default_action = "BLOCK_ENTRY"
    try:
        with open(p, encoding="utf-8") as fh:
            cal = json.load(fh)
    except FileNotFoundError:
        raise CalendarUnavailable(f"{os.path.relpath(p, ROOT)} does not exist -- CLAUDE.md §32 forbids "
                                  f"reading a missing calendar as 'no news'", default_action)
    except (OSError, ValueError) as exc:
        raise CalendarUnavailable(f"{os.path.relpath(p, ROOT)} is unreadable or malformed ({exc}); an "
                                  f"unparseable calendar is not an empty one", default_action)

    action = ((cal.get("policy") or {}).get("fail_safe") or {}).get("action", default_action)
    if action not in FAIL_SAFE_ACTIONS:
        raise CalendarUnavailable(f"fail_safe.action {action!r} is not one of {list(FAIL_SAFE_ACTIONS)}",
                                  default_action)
    snap = cal.get("snapshot") or {}
    if not snap.get("id"):
        raise CalendarUnavailable("the calendar carries no snapshot id, so a decision made against it "
                                  "could not say which calendar state it saw (CLAUDE.md §29)", action)
    through = snap.get("covers_through")
    if not through:
        raise CalendarUnavailable("the calendar declares no `covers_through`, so it cannot say where its "
                                  "claim ends and silence begins (CLAUDE.md §29/§32)", action)
    now = _parse(at) if at else datetime.datetime.now(datetime.timezone.utc)
    if now > _parse(through):
        raise CalendarUnavailable(
            f"the calendar covers through {through} and it is now {now.isoformat()}: it makes no claim "
            f"about this moment. An unmaintained calendar is a data-quality gap, not a clean bill of "
            f"health (CLAUDE.md §29, §32)", action)
    return cal


def instrument_currencies(symbol, cal):
    """The currencies an instrument quotes, plus any declared aliases (§26).

    Derived from the canonical id (`XAU/USD` -> XAU, USD), not from a second per-symbol table: a currency
    list keyed by symbol would be a copy of the identity instruments.json already owns.
    """
    aliases = ((cal.get("relevance") or {}).get("currency_aliases") or {})
    out = set()
    for part in I.canonical(symbol).split("/"):
        out.add(part)
        out.update(aliases.get(part, []))
    return out


def relevant(event, symbol, cal):
    """Does this event reach this instrument? §26: not everything reaches everything."""
    glob = (cal.get("relevance") or {}).get("global_keyword", "GLOBAL")
    cur = {c.upper() for c in (event.get("currencies") or [])}
    if glob in cur:
        return True
    if cur & {c.upper() for c in instrument_currencies(symbol, cal)}:
        return True
    classes = {c.lower() for c in (event.get("asset_classes") or [])}
    if classes and (I.display(symbol).get("asset_class") or "").lower() in classes:
        return True
    countries = {c.upper() for c in (event.get("countries") or [])}
    if countries and (I.display(symbol).get("country") or "").upper() in countries:
        return True
    return False


def effective_time(event, decision_time=None):
    """Which timestamp this event's window is built around (§27).

    Before the release, the best-known scheduled time. After it, the ACTUAL time where it is reliably
    known. The point-in-time rule is what keeps this honest: an `actual_release_time` is only used when it
    was already available at `decision_time` -- otherwise a time learned later would silently move a window
    that an earlier decision was judged against, which §27 and §28 both forbid.
    """
    sched = event.get("scheduled_event_time")
    actual = event.get("actual_release_time")
    if not actual:
        return _parse(sched), "scheduled"
    if decision_time is not None and _parse(event.get("available_time") or sched) > _parse(decision_time):
        return _parse(sched), "scheduled"
    return _parse(actual), "actual"


def visible(event, decision_time):
    """§28: an event exists for a decision only once it was available. No decision_time = no filtering."""
    if decision_time is None:
        return True
    avail = event.get("available_time") or event.get("scheduled_event_time")
    return _parse(avail) <= _parse(decision_time)


def restricted(event, cal):
    """Whether this event's impact is restricted under the active policy (§25)."""
    impact = (event.get("impact") or "UNKNOWN").upper()
    if impact not in IMPACTS:
        raise CalendarUnavailable(f"event {event.get('id')!r} declares impact {impact!r}, which is not one "
                                  f"of {list(IMPACTS)} (CLAUDE.md §25)",
                                  ((cal.get("policy") or {}).get("fail_safe") or {}).get("action",
                                                                                         "BLOCK_ENTRY"))
    return bool(((cal.get("policy") or {}).get("by_impact") or {}).get(impact, {}).get("restricted"))


def windows(symbol, cal=None, decision_time=None, at=None, mode=None):
    """The restricted windows for this instrument, as a MERGED UNION (§30).

    Overlapping events produce the union of their windows and adjacent windows are joined, so a break can
    never appear between two events that together cover a stretch. That is the defect the previous
    implementation demonstrated: a three-hour window parsed as two point events with two unprotected hours
    between them.

    Returns a list of `(start, end, [events])`, sorted, non-overlapping.
    """
    cal = cal if cal is not None else load(at=at)
    pol = cal.get("policy") or {}
    pre, post = pol.get("pre_minutes", 10), pol.get("post_minutes", 10)
    strict_unknown = bool((pol.get("by_impact") or {}).get("UNKNOWN", {}).get("strict_no_trade"))

    spans = []
    for ev in cal.get("events") or []:
        if ev.get("status") == "cancelled" or not visible(ev, decision_time) or not relevant(ev, symbol, cal):
            continue
        impact = (ev.get("impact") or "UNKNOWN").upper()
        # §25: UNKNOWN is not LOW. It does not restrict by default, but STRICT mode may say it does -- and
        # that is a mode question, so the mode has to be passed in rather than guessed here.
        gates = restricted(ev, cal) or (impact == "UNKNOWN" and strict_unknown and mode == "STRICT")
        if not gates:
            continue
        t, basis = effective_time(ev, decision_time)
        a = t - datetime.timedelta(minutes=ev.get("pre_minutes") if ev.get("pre_minutes") is not None else pre)
        b = t + datetime.timedelta(minutes=ev.get("post_minutes") if ev.get("post_minutes") is not None else post)
        spans.append((a, b, dict(ev, _basis=basis, _effective_time=t.isoformat().replace("+00:00", "Z"))))

    spans.sort(key=lambda s: s[0])
    merged = []
    for a, b, ev in spans:
        if merged and a <= merged[-1][1]:          # `<=`, not `<`: adjacent windows touch and must join,
            prev = merged[-1]                      # or a single instant between them would read as clear
            merged[-1] = (prev[0], max(prev[1], b), prev[2] + [ev])
        else:
            merged.append((a, b, [ev]))
    return merged


def state(symbol, at=None, decision_time=None, cal=None, mode=None, path=None):
    """The event-risk state for one instrument at one instant.

    Returns `(state, reason, events)` where state is CLEAR / BLOCKED / UNAVAILABLE. UNAVAILABLE carries the
    CONFIGURED fail-safe in its reason and is never silently a CLEAR -- that is the whole of §32.

    `at` is the moment being judged; `decision_time` is when the decision is being made, and defaults to
    `at`. They differ in a backtest, where `at` walks history and `decision_time` walks with it.
    """
    when = _parse(at) if at else datetime.datetime.now(datetime.timezone.utc)
    dt = decision_time if decision_time is not None else when
    try:
        cal = cal if cal is not None else load(path=path, at=when)
        wins = windows(symbol, cal=cal, decision_time=dt, mode=mode)
    except CalendarUnavailable as exc:
        return UNAVAILABLE, f"{exc.reason} -> configured fail-safe: {exc.action}", []
    for a, b, evs in wins:
        if a <= when <= b:
            names = ", ".join(f"{e['name']} ({e['impact']}, {e['_basis']} {e['_effective_time']})"
                              for e in evs)
            return BLOCKED, (f"inside a restricted window {a.isoformat()} - {b.isoformat()} for {names}"
                             + (f"; {len(evs)} overlapping events merged" if len(evs) > 1 else "")), evs
    return CLEAR, (f"no restricted window covers {when.isoformat()} for {symbol} "
                   f"(calendar {cal['snapshot']['id']})"), []


def blocked(symbol, at=None, decision_time=None, cal=None, mode=None, path=None):
    """(True, reason) when a NEW ENTRY must not be taken. §31: this is about entries, not open positions."""
    st, why, _ = state(symbol, at=at, decision_time=decision_time, cal=cal, mode=mode, path=path)
    return st != CLEAR, why


def existing_position_action(cal=None, at=None):
    """§31: what an OPEN position does when a release approaches -- configured, never automatic."""
    try:
        cal = cal if cal is not None else load(at=at)
    except CalendarUnavailable:
        # A missing calendar blocks new entries (§32); it does not reach into open positions and start
        # closing them. Doing nothing to an existing position is the conservative answer here, and the
        # opposite of the one §32 asks for on entry -- deliberately, because the risks are not symmetric.
        return "HOLD"
    a = ((cal.get("policy") or {}).get("existing_positions") or {}).get("action", "HOLD")
    return a if a in POSITION_ACTIONS else "HOLD"


def snapshot(cal=None, at=None):
    """The calendar state identifier a research record must carry (§29, §10, §11)."""
    try:
        cal = cal if cal is not None else load(at=at)
    except CalendarUnavailable as exc:
        return {"id": None, "unavailable": exc.reason, "fail_safe": exc.action}
    return dict(cal["snapshot"])
