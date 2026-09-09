# Event Calendar

Read by DecisionAgent's Event-Risk gate (`SYSTEM-DESIGN.md` §6.3). **This file has no automatic feed in v1** — it is maintained by hand (or proposed via `/improve`, never silently). If today's date isn't covered by an entry below, Event Risk MUST be reported `UNKNOWN`, not `LOW`.

Format: one row per known event, with a blackout window (avoid new entries inside this window per the master spec §6).

| Date (UTC) | Event | Blackout window | Affects |
|---|---|---|---|
| _(none scheduled yet — add entries here)_ | | | |

## How to add an entry

`| 2026-09-18 | FOMC Rate Decision | 2026-09-18T17:00Z – 2026-09-18T20:00Z | BTC, ETH, SOL, XAUUSD, XAGUSD, USOIL, UKOIL |`

Typical recurring events to track: CPI, FOMC decisions/speeches, NFP, EIA weekly petroleum status, OPEC+ meetings, major scheduled crypto-specific events (network upgrades, large token unlocks). Keep this list current — a stale calendar degrades every future `/analyze` call's Event-Risk gate to `UNKNOWN`, which itself should reduce confidence per the master spec's data-quality discipline.
