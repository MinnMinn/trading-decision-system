"""CLAUDE.md §52 -- THE tracker for docs/architecture/feed-health.json: what a polling feed does instead of a
socket, and how it goes wrong silently.

§52 is written for a WebSocket and this repo has none: crypto is Binance REST polling, CFD is an MT5 file
export. Four of its ten requirements are genuinely about a connection nobody opens, and they are declared
`not_applicable` **with the reason** rather than omitted -- an omitted requirement is one nobody can tell was
considered, and the day a socket is opened that file is the list of what it must then do.

The sentence that survives any transport is this one:

    "Do not trade from silently stale state."

The word is **silently**. §20 already catches the faults that live INSIDE one response -- a duplicate bar, a
hole, a backwards timestamp, a stale `last_updated`. What nothing caught is the faults that only exist
BETWEEN polls:

* the same bytes coming back for an hour (a stalled MT5 export, a cached endpoint) -- every individual
  response is perfectly valid and perfectly fresh-looking;
* bars missing between one poll's newest bar and the next poll's oldest;
* a poll whose newest bar is OLDER than the previous poll's;
* a bar that had already closed coming back with different values -- §8's provider correction, arriving live.

    import feed_health as FH

    st = FH.observe("binance_public", "BTCUSDT", "15m", candles, last_updated=...)
    st["state"]            -> 'STALLED'
    FH.as_quality(st)      -> 'STALE'     # §52: feed health feeds the SAME §20 rules, it does not invent an action

Two decisions worth stating:

1. **UNKNOWN is not healthy.** The first observation after a restart knows nothing, and treating that as
   health is how a restart launders a stalled feed.
2. **This module maps onto §20's vocabulary; it does not decide.** §52 says realtime data quality must feed
   into the same data-quality and required-analysis rules the Decision Engine already uses. One gate, one
   vocabulary -- a second, quieter gate here would be a second place for an entry to be allowed.
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

PATH = os.path.join(ROOT, "docs", "architecture", "feed-health.json")
STATE = os.path.join(ROOT, "data", "live", "feed-health.json")

HEALTHY, STALLED, GAPPED, REGRESSED, REVISED, UNKNOWN = (
    "HEALTHY", "STALLED", "GAPPED", "REGRESSED", "REVISED", "UNKNOWN")

#: Seconds per timeframe. A stall is measured against the BAR, not against the poll count.
TF_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1H": 3600, "2H": 7200, "4H": 14400,
              "1D": 86400, "1W": 604800}

#: How many timeframes may pass with no new bar before a feed is STALLED. Matches §20's own staleness
#: tolerance in spirit: one missed bar can be a slow exporter, two is a feed that stopped.
STALL_AFTER_BARS = 2


class RegistryError(ValueError):
    """The §52 registry itself is wrong -- raised at import."""


class NotDeclared(KeyError):
    """Something named a §52 requirement the spec does not list."""


def _load(path=None):
    path = path or PATH
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    reqs = data.get("requirements")
    if not isinstance(reqs, list) or not reqs:
        raise RegistryError(f"{path}: `requirements` must be a non-empty list")
    for r in reqs:
        for f in ("id", "spec_name", "applies"):
            if r.get(f) is None:
                raise RegistryError(f"{path}: requirement {r.get('id')!r} has no {f!r}")
        if r["applies"] is False and not str(r.get("_why") or "").strip():
            raise RegistryError(
                f"{path}: requirement {r['id']!r} is declared not applicable and does not say why. §52's list "
                f"is about a transport this repo does not use, and 'not applicable' without a reason is "
                f"indistinguishable from 'not done'.")
        if r["applies"] is False and not str(r.get("becomes_applicable_when") or "").strip():
            raise RegistryError(f"{path}: requirement {r['id']!r} must say what would make it apply -- "
                                f"otherwise the exemption outlives the transport that justified it")
        if r["applies"] is True and not str(r.get("implemented_by") or "").strip():
            raise RegistryError(f"{path}: requirement {r['id']!r} applies and names no implementation")
    if UNKNOWN not in (data.get("states") or {}):
        raise RegistryError(f"{path}: `states` must include {UNKNOWN!r}")
    if "NOT healthy" not in data["states"][UNKNOWN]:
        raise RegistryError(
            f"{path}: the {UNKNOWN!r} state must say it is not healthy -- the first poll after a restart "
            f"knows nothing, and treating that as health is how a restart launders a stalled feed.")
    return data


_DATA = _load()
REQUIREMENTS = {r["id"]: r for r in _DATA["requirements"]}
REQ_ORDER = tuple(r["id"] for r in _DATA["requirements"])
APPLICABLE = tuple(r for r in REQ_ORDER if REQUIREMENTS[r]["applies"])
NOT_APPLICABLE = tuple(r for r in REQ_ORDER if not REQUIREMENTS[r]["applies"])
STATES = tuple(_DATA["states"])


def requirement(rid):
    r = REQUIREMENTS.get(rid)
    if r is None:
        raise NotDeclared(f"no §52 requirement {rid!r}; the ten are {list(REQ_ORDER)}")
    return r


def spec_name(rid):
    return requirement(rid)["spec_name"]


def _fingerprint(candles):
    """A stable digest of a candle series, so 'did this poll return anything new' is one comparison."""
    payload = [[c.get("time"), c.get("open"), c.get("high"), c.get("low"), c.get("close")]
               for c in candles or ()]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _closed_map(candles, *, keep=200):
    """The last `keep` bars as {time: (o,h,l,c)} -- the window a revision is looked for in.

    Bounded on purpose: a full history would make the state file grow without limit, and a provider that
    revises a bar from last year is a different problem from one revising the bar it just closed.
    """
    return {c["time"]: [c.get("open"), c.get("high"), c.get("low"), c.get("close")]
            for c in (candles or ())[-keep:] if c.get("time")}


def _overdue(newest, now, timeframe):
    """How long past due a feed is, or None. Measured against the BAR, not against the poll count."""
    step = TF_SECONDS.get(timeframe)
    if not (step and newest and now):
        return None
    try:
        import datetime
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        age = (datetime.datetime.strptime(now, fmt) - datetime.datetime.strptime(newest, fmt)).total_seconds()
    except (ValueError, TypeError):
        return None
    # `newest` is the OPEN time of the newest closed bar, so one full step is expected before the next one.
    return f"{age / 60:.0f} min" if age > step * (STALL_AFTER_BARS + 1) else None


def _load_state(path=None):
    p = path or STATE
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_state(d, path=None):
    p = path or STATE
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)
    except OSError:
        pass                      # observation must never fail a tick (§1: safety above measurement)


def observe(provider, symbol, timeframe, candles, *, last_updated=None, now=None, path=None, keep=200):
    """Record one poll and return what it says about the feed.

    Compares against the PREVIOUS poll of the same (provider, symbol, timeframe). Everything it can detect is
    invisible to a single response: a stalled feed returns perfectly valid, perfectly fresh-looking bars.
    """
    key = f"{provider}|{symbol}|{timeframe}"
    store = _load_state(path)
    prev = store.get(key)
    cur_fp = _fingerprint(candles)
    newest = candles[-1]["time"] if candles else None
    closed = _closed_map(candles, keep=keep)

    findings = []
    state = HEALTHY
    if prev is None:
        state = UNKNOWN
        findings.append("no prior observation for this feed")
    else:
        # sequence validation: did the feed go backwards?
        if newest and prev.get("newest") and newest < prev["newest"]:
            state = REGRESSED
            findings.append(f"newest bar went backwards: {prev['newest']} -> {newest}")
        elif prev.get("count") and len(candles or ()) < prev["count"] * 0.5:
            state = REGRESSED
            findings.append(f"bar count fell from {prev['count']} to {len(candles or ())}")
        # duplicate detection: an identical response.
        #
        # An identical poll is NOT by itself evidence of anything -- a 15m feed polled three times inside one
        # bar is SUPPOSED to return the same closed bars, and the first version of this check called every
        # feed in the repo stalled when three ticks ran inside a minute.
        #
        # A second version compared `last_updated`: if the source advanced it while the bars stood still, the
        # source was claiming freshness it did not have. That is a real failure mode -- and it is NOT this
        # repo's. `scripts/fetch-binance-klines.sh` stamps `last_updated` with the FETCH time, so it advances
        # on every poll by design, and the check called all 28 crypto feeds stalled. Running it is what
        # showed that; reading the field's name would not have.
        #
        # What is left is the signal that does not depend on any of that: enough wall clock has passed that a
        # new bar MUST exist by now, and none does. A feed that stopped being written is caught by that and
        # by §20's own STALE check on `last_updated`, which is the fetch-time field doing the job it is for.
        elif cur_fp == prev.get("fingerprint"):
            overdue = _overdue(newest, now, timeframe)
            if overdue:
                state = STALLED
                findings.append(f"no new bar for {overdue} -- more than {STALL_AFTER_BARS} x {timeframe} "
                                f"since {newest}; the feed is not advancing")
        else:
            # revision: a bar that had ALREADY CLOSED came back different (§8's provider correction, arriving
            # live). The newest bar is excluded -- the forming bar is expected to move, and calling that a
            # revision would flag every healthy poll.
            revised = [t for t, v in closed.items()
                       if t in (prev.get("closed") or {}) and t != newest and prev["closed"][t] != v]
            if revised:
                state = REVISED
                findings.append(f"{len(revised)} already-closed bar(s) came back with different values, "
                                f"e.g. {sorted(revised)[0]}")
            else:
                # gap detection BETWEEN polls: this poll starts after the previous poll's newest bar, so the
                # bars in between were never seen by anything. §20 cannot see this -- each response is whole.
                oldest = candles[0]["time"] if candles else None
                if oldest and prev.get("newest") and oldest > prev["newest"]:
                    state = GAPPED
                    findings.append(f"this poll starts at {oldest}, after the previous poll's newest bar "
                                    f"{prev['newest']}; the bars between were never seen")
    unchanged = (int((prev or {}).get("unchanged_polls", 0)) + 1) if (prev and cur_fp == prev.get("fingerprint")) else 0
    recovered = bool(prev and prev.get("state") not in (None, HEALTHY, UNKNOWN) and state == HEALTHY)
    if recovered:
        findings.append(f"recovered from {prev['state']}")

    store[key] = {"provider": provider, "symbol": symbol, "timeframe": timeframe,
                  "fingerprint": cur_fp, "newest": newest, "count": len(candles or ()),
                  "closed": closed, "unchanged_polls": unchanged, "state": state,
                  "last_updated": last_updated, "observed_at": now,
                  "previous_state": (prev or {}).get("state"),
                  "incidents": ((prev or {}).get("incidents", 0) + (1 if state not in (HEALTHY, UNKNOWN) else 0))}
    _save_state(store, path)
    return {"key": key, "state": state, "findings": findings, "recovered": recovered,
            "unchanged_polls": unchanged, "newest": newest,
            "incidents": store[key]["incidents"],
            "_source": "docs/architecture/feed-health.json (CLAUDE.md §52)"}


def health(path=None):
    """Every tracked feed's current state. `provider health` (§52) is the aggregate of these."""
    store = _load_state(path)
    by_provider = {}
    for key, rec in store.items():
        p = rec.get("provider")
        b = by_provider.setdefault(p, {"feeds": 0, "unhealthy": [], "incidents": 0})
        b["feeds"] += 1
        b["incidents"] += int(rec.get("incidents") or 0)
        if rec.get("state") not in (HEALTHY,):
            b["unhealthy"].append({"feed": key, "state": rec.get("state")})
    return {"feeds": store, "by_provider": by_provider,
            "_source": "docs/architecture/feed-health.json (CLAUDE.md §52)"}


def as_quality(observation):
    """Map a §52 feed state onto §20's vocabulary.

    §52: 'Realtime data quality must feed into the same data-quality and required-analysis rules used by the
    Decision Engine.' So this module does NOT invent an action -- it hands §20 a state and §20's existing
    gate decides what that does to an entry. A second, quieter gate here would be a second place for an entry
    to be allowed.
    """
    import quality as Q
    state = observation["state"] if isinstance(observation, dict) else observation
    mapped = {HEALTHY: "FRESH",
              STALLED: "STALE",        # the feed is not advancing; §20 maps STALE -> WAIT
              GAPPED: "PARTIAL",       # bars were never seen; §20 maps PARTIAL -> BLOCK_ENTRY
              REGRESSED: "INVALID",    # a feed that goes backwards is not a series
              REVISED: "INVALID",      # the provider withdrew information a decision may already have used
              UNKNOWN: "UNKNOWN"}[state]
    if mapped not in Q.STATES:
        raise RegistryError(f"{mapped!r} is not one of §20's states")
    return mapped


def describe(path=None):
    h = health(path)
    if not h["feeds"]:
        return "§52 feed health: no feed has been observed yet"
    lines = [f"§52 feed health: {len(h['feeds'])} feed(s)"]
    for pid, b in sorted(h["by_provider"].items()):
        bad = ", ".join(f"{u['feed'].split('|', 1)[1]}={u['state']}" for u in b["unhealthy"]) or "all healthy"
        lines.append(f"  {pid:<18} feeds={b['feeds']:<3} incidents={b['incidents']:<4} {bad}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(f"CLAUDE.md §52 -- {len(REQ_ORDER)} requirements: {len(APPLICABLE)} apply to this transport, "
          f"{len(NOT_APPLICABLE)} do not\n")
    for rid in REQ_ORDER:
        r = REQUIREMENTS[rid]
        if r["applies"]:
            print(f"  [x] {r['spec_name']:<24} {r['implemented_by'][:90]}")
        else:
            print(f"  [ ] {r['spec_name']:<24} N/A: {r['_why'][:80]}")
    print()
    print(describe())
