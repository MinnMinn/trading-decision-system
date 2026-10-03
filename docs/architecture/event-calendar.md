# Event Calendar

**The calendar itself is `docs/architecture/event-calendar.json`.** This page explains it; the JSON is the
source, `scripts/event_risk.py` is the one reader, and `scripts/tests/test_event_risk.py` (62 tests) holds
it to CLAUDE.md §24-§32.

## Why this file stopped being the calendar (2026-09-18)

It used to BE the calendar -- a markdown table -- and `strategy-runner.event_blackout` read it with a regex
for `YYYY-MM-DD HH:MM` over the **entire file**, blocking within +/-30 minutes of any match. Three
consequences, all live on the code path that places orders:

1. **The "How to add an entry" example below was a live blackout window.** A documentation line restricted
   real trading, because the parser could not tell prose from data.
2. **A row written `17:00Z - 20:00Z` parsed as two POINT events**, leaving **17:30-19:30 unprotected** inside
   a three-hour FOMC window -- the accidental gap CLAUDE.md §30 explicitly forbids.
3. **Every failure returned "no blackout".** Missing file, unreadable file, empty table -- all read as
   *no news*, which is the one thing §32 says never to assume.

None of that was fixable by improving the regex, because the input was never a data format.

## What the JSON gives you that a table could not

| Need | Where |
|---|---|
| §24 configurable 10-minute pre/post buffers | `policy.pre_minutes` / `post_minutes`, overridable per event |
| §25 HIGH / MEDIUM / LOW / UNKNOWN, UNKNOWN never treated as LOW | `policy.by_impact` |
| §26 an event reaches only the instruments it is relevant to | `currencies` / `countries` / `asset_classes` per event, matched against the instrument's canonical id |
| §27 scheduled vs actual release time, kept apart | `scheduled_event_time`, `actual_release_time` |
| §28 point-in-time visibility | `available_time` per event |
| §29 which calendar state a decision saw | `snapshot.id` / `version` / `covers_through` |
| §30 overlapping windows unioned, no gaps | computed in `event_risk.windows()` |
| §31 what an OPEN position does | `policy.existing_positions.action` (default HOLD) |
| §32 what a missing/stale/invalid calendar does | `policy.fail_safe.action` (default BLOCK_ENTRY) |

## How to add an entry

Edit `event-calendar.json` and append to `events`:

```json
{
  "id": "fomc-2026-09-18",
  "name": "FOMC Rate Decision",
  "impact": "HIGH",
  "scheduled_event_time": "2026-09-18T18:00:00Z",
  "actual_release_time": null,
  "available_time": "2026-09-01T00:00:00Z",
  "status": "scheduled",
  "currencies": ["USD"],
  "countries": ["US"],
  "asset_classes": []
}
```

`available_time` is **when the row became knowable**, not when the event happens -- it is what stops a row
added today from silently applying to a backtest of last month. Then move `snapshot.covers_through` forward
and bump `snapshot.version`; the id changes whenever the content does, so a research record can say which
state it read.

Typical recurring events to track: CPI, FOMC decisions and speeches, NFP, EIA weekly petroleum status,
OPEC+ meetings, and scheduled crypto-specific events (network upgrades, large token unlocks).

## Current snapshot

`cal-2026-10-03-a` (v2) covers through **2026-12-31**: the scheduled HIGH-impact US releases (FOMC
decision and press conference, NFP, CPI, PCE, GDP advance), ECB decisions and press conferences, and RBA
decisions, each with its official schedule page in `source` and the publisher's local clock in
`local_time`. Its `_v2_scope` note lists what is deliberately not covered and why every row's
`available_time` is the curation date. **Before 2026-12-31, extend the file** -- otherwise the fail-safe
blocks all new entries from 2027-01-01.

**A stale calendar is not a quiet one.** Past `covers_through`, every instrument reads UNAVAILABLE and the
configured fail-safe applies -- by design, so that forgetting to maintain this file is loud rather than
invisible.
