# FTMO-Demo server timezone -- measured, not read off the name

CLAUDE.md §8/§20/§59: a wrong zone here is a silent one-hour error in every bar of every fund-search
backtest. This is the same measurement `docs/architecture/mt5-history-export.md` did for `mt5_bridge`
(MetaQuotes-Demo, resolved to `Europe/Helsinki`), repeated for the second MT5 server, `FTMO-Demo`, whose
`ExportHistory.mq5` output landed in `Common\Files` on 2026-09-28/29 (owner decision, `docs/plans/2026-09-28-methodology-improvement-plan.md` §6 items 3, 7).

## The candidate hypotheses

The dispatch names the two conventions MT5 CFD brokers commonly use for their server clock:

* **EU-date convention** -- the server clock changes on the EU's DST weekends (last Sunday of March / last
  Sunday of October), same magnitude as EET (+02:00 winter / +03:00 summer). This is what MetaQuotes-Demo
  measured to.
* **US-date convention** -- the server clock keeps the same +02:00/+03:00 magnitude but changes on the US
  market's DST weekends (2nd Sunday of March / 1st Sunday of November).

`_server_utc_offset_sec_now = 10801` in the 2026-09-28 export (UTC+3) does not distinguish these: both EU and
US are in DST on that date. The two conventions only disagree during the two short calendar windows where EU
and US DST dates differ:

* **Gap A** (mid-to-late March): US already sprang forward, EU has not yet -- roughly 2nd Sunday March to
  last Sunday March.
* **Gap B** (late October / early November): EU has already fallen back, US has not yet -- roughly last
  Sunday October to 1st Sunday November.

## Method (reused from the MetaQuotes-Demo measurement)

`docs/architecture/mt5-history-export.md` found MetaQuotes-Demo's busiest server-local hour is 16:00 in both
deep summer and deep winter (the NY-session-open anchor and the broker's own DST both shift together most of
the year), but **drops to 15:00** during the mid-March gap window -- direct evidence the broker's own clock
had NOT yet moved while the underlying (US-anchored) session activity already had, i.e. an EU-date broker.

The same test distinguishes the two hypotheses in general: if the broker's clock changes on the **same**
calendar weekend as the underlying US-anchored session activity (US-date convention), the local peak hour
should show **no shift** in either gap window, because both the broker's clock and the session anchor move
together. If the broker changes on EU dates, the local peak hour should show a ~1-hour shift in **both** gap
windows (the same direction, since exactly one of {broker offset, session anchor} has moved in each case).

### Implementation

Source: `history.XAUUSD.15m.json` and `history.US500.cash.15m.json` (raw FTMO-Demo server time, `_server:
"FTMO-Demo"`), read directly from `Common\Files` (read-only; the exports are not committed to the repo).
Tuesday/Wednesday/Thursday bars only (excludes the Monday weekly-open and Friday weekly-close gap
artifacts, which otherwise dominate the high-low range statistic at hour 0). For each year 2013-2025:

* **baseline** windows: a full month deep in January and a full month deep in June/July (both EU and US
  unambiguously on the same DST state).
* **gap A** window: `[2nd-Sunday-March, last-Sunday-March)`.
* **gap B** window: `[last-Sunday-October, 1st-Sunday-November)`.

For each window, the mean `(high - low)` range per server-local hour-of-day (08:00-18:00, the London/NY
session core) is pooled across all years into one profile. The gap-window profile is then compared against
the baseline profile at integer hour shifts of -1, 0, +1 using Pearson correlation; the shift that
correlates best identifies whether the gap week's activity pattern looks like the baseline shifted (EU-date
convention) or unshifted (US-date convention).

## Result

**XAUUSD 15m, Tue-Thu, hours 08-18, pooled 2013-2025** (baseline n=20,382; gap A n=5,938; gap B n=2,340):

| window | shift -1 | shift 0 | shift +1 |
|---|---|---|---|
| gap A (March) | 0.8554 | **0.9213** | 0.5704 |
| gap B (Oct/Nov) | 0.8542 | **0.9329** | 0.5802 |

**US500.cash 15m, Tue-Thu, hours 08-18, pooled 2013-2025** (baseline n=6,500; gap A n=1,890; gap B n=900,
account only carries history from 2017-12-29):

| window | shift -1 | shift 0 | shift +1 |
|---|---|---|---|
| gap A (March) | 0.8333 | **0.9739** | 0.8507 |
| gap B (Oct/Nov) | 0.7589 | **0.9694** | 0.8268 |

Both instruments, both gap windows: **shift 0 wins decisively**. The gap-week local-hour profile matches the
baseline profile with no shift -- the opposite of what MetaQuotes-Demo measured (which needed shift -1, i.e.
a 1-hour-earlier dip, during gap A). An early per-year single-week argmax pass (not reproduced above) was too
noisy to read (a Tue-Thu week is only ~36 bars per hour); the pooled-correlation version above is the
evidence this conclusion rests on.

## Conclusion

**FTMO-Demo's server clock changes on the US market's DST calendar, not the EU's**, at the EET-sized
magnitude already measured from `_server_utc_offset_sec_now` (+02:00 standard / +03:00 DST). This is not a
real IANA zone -- no geography-tied zone transitions on a different region's calendar dates by construction
-- so it is declared in `docs/architecture/providers.json` as a named **convention**
(`server_timezone_convention: "us_dst_dates_fixed_offset"`, `server_utc_offset_standard_sec: 7200`,
`server_utc_offset_dst_sec: 10800`) on a new provider entry `mt5_bridge_ftmo`, rather than a
`server_timezone` Region/City string. `scripts/mt5_time.py` implements it as `UsDatesFixedOffsetZone`, which
reads the US DST transition **instants** from the real `America/New_York` zoneinfo object (so historical US
rule changes, e.g. the 2007 date change, are inherited correctly rather than hardcoded) and substitutes the
fixed 7200s/10800s offset magnitude for New York's own -5h/-4h.

## What this does NOT resolve

* This measurement used only two instruments (XAUUSD, US500.cash) and only 15m bars. The importer applies
  the same convention to every FTMO-Demo symbol and timeframe; if a future export shows a different pattern
  for another instrument, that is new evidence and should reopen this finding, not be silently absorbed.
* Years before 2013 were excluded from the pooled analysis (kept for the raw per-year table only) because the
  single-week argmax pass was unusably noisy that far back and a pooled profile was not built for them; this
  does not mean the convention changed, only that it was not separately re-verified there.
