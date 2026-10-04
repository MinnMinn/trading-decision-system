# Family CAL -- scheduled-calendar premia on the US index CFDs: pre-FOMC drift and the pre-holiday effect -- pre-registration DRAFT (2026-10-04) [CAL-P1]

Status: DRAFT. Not sealed.

Sealing: the coordinator commits this text, after review, as
`docs/plans/2026-10-04-cal-us-index-calendar-preregistration.md`, with the status line above replaced by a line that reads
exactly "Status: SEALED" and with §10's code manifest filled in. `scripts/research/edge_cal.py` refuses the read until then
(scripts/research/prereg_guard.py `require_sealed`, `require_fingerprint`).

**No outcome of this family has been read.** Code tested on hand-built bars and a synthetic calendar only
(`scripts/tests/test_edge_cal.py`). Revised once after a review (2026-10-04): the first draft re-opened two classes that
earlier verdicts had closed or limited to forward data, without citing them (CLAUDE.md §53).

## 0. Earlier verdicts, and why this family is FORWARD-ONLY by default

- **Pre-holiday** is part of B6, "calendar effects (turn of month, month end, pre-holiday) with a calendar null": "history
  CONTAMINATED (G7 / H2 read): forward only ... forward pre-registration only (round A: no re-read of read data)"
  (docs/plans/2026-10-03-candidates.md:44). The crypto / CFD sweep: "Pre-holiday: no source, and MDE about 32 bp"
  (docs/plans/2026-10-03-crypto-cfd-design.md:263).
- **Pre-FOMC** is B5 (candidates.md:43). The sweep: "Pre-FOMC drift: decayed after 2015. Forward-only at most"
  (crypto-cfd-design.md:248; also :32).
- The first draft's argument for a history read -- every family since the census measured the excess over the same-minute
  placebo, which removes calendar premia by construction (docs/plans/2026-10-03-reframes.md:188-193) -- is not new
  evidence against B6. B6 is about which days' returns were read, not about how they were measured.
- **Contamination, counted (calendar only, no prices).** On US500 / US30 / USTEC:
  - G7 read the full server-day return, long, on every turn-of-month day (the last weekday with bars of a month and its
    first 3; scripts/research/edge_f4.py:157-176), in all three F4 reads; its nets were positive (docs/audits/
    2026-10-02-edge-f4.md:81-83). 24 of the 72 pre-holiday days from 2019-02-11 to 2026-09-25 are such days.
  - M1's discovery read (2018-01 -> 2021-08) computed the open -> close return of the next NYSE day after each week-4 day,
    after each falsification placebo day it kept, and after the first-business-day reversal day, and it reported OLS
    intercepts (mean returns) for them (scripts/research/edge_m1.py:654-701, :807-824). That is 855 of the 923 NYSE days
    of those months.
  - Of the 83 pre-holiday days from 2017-12-28 to 2026-09-25, 44 fall on a turn-of-month day (NYSE proxy) or an M1 read
    day. The dry run gives the per-series counts (G7's days come from each series, `edge_f4.tom_days`).
- **Default: forward only.** T1 and T2 are tested on event days after the seal, once.
- **Owner override (not the default).** The owner may override B6 for a single history read. The override must be recorded
  in this text before sealing, with its reason, and the coordinator sets `HISTORICAL_READ = True` in
  `scripts/research/edge_cal.py` (the code fingerprint pins it). Even then the read never computes a row on a G7
  turn-of-month day or an M1 read day: those days are skipped before any price of the day is touched, counted, and kept
  out of the calendar null. With them removed, the history read has roughly 39 pre-holiday and a similar fraction of FOMC
  days left: MDE ~40 bp or more.

Owner override of B6 for a history read: NO (default; change before sealing only on the owner's recorded decision).

## 1. Events and windows (long only)

Server day D = 17:00 New York on D - 1 -> 17:00 New York on D (FTMO-Demo clock; the US index CFD session starts 01:05
server = 18:05 New York the evening before). Every trade lives inside one server day: no swap.

- **T1 PRE-FOMC.** D = a SCHEDULED FOMC announcement date. Entry: OPEN of server day D's first bar. Exit: CLOSE of the 5m bar
  that OPENS 10 minutes before the announcement (it closes 5 minutes before; flat before the statement). The window is
  close to Lucca and Moench's 24 hours before the statement, minus the previous afternoon.
  - The calendar file carries each date's announcement time in New York time; the code never assumes 14:00.
  - Excluded: unscheduled (intermeeting) actions, not knowable in advance; and any scheduled date whose announcement did
    not happen as scheduled (the file flags it `cancelled`; it is known before that day starts).
- **T2 PRE-HOLIDAY.** D = the last NYSE business day before a regular NYSE holiday (`edge_m1.nyse_holidays`,
  scripts/research/edge_m1.py:219, tested in M1). The two special closures (days of mourning, edge_m1.py:180) are not
  holidays here. Entry: OPEN of D's first bar. Exit: CLOSE of the bar opening 12:50 New York (closes 12:55): before any
  13:00 early close, so no early-close list is needed. The afternoon is not measured (disclosed).
- **Eligibility** (both): D's previous server day is dense (`edge_census.Series.prev_dense`), D has a sigma
  (`sigma_every_day`: the previous 20 dense days, point in time), and the exit bar exists in D.

## 2. Measurement

- r = C[exit] / O[entry] - 1 (long).
- **Calendar null.** excess = r - the mean r of the SAME window (first bar of the server day -> the bar opening at the same
  New York clock time) over every other NYSE business day of the same symbol and calendar year that is neither an event
  day nor an excluded read day. Forward: only days on or after the seal date. A per-year null absorbs each year's drift.
- scale = sigma_5m x sqrt(bars held); excess z = excess / scale.
- Cost: one relative spread per round trip at the legs' table buckets (`edge_census.Costs.round_trip_at`, profile
  `ftmo_demo_2026_09_relspread`, server-hour frame). Stress: the p90 spread.
- Statistics: `edge_census.summarise`, pooled over the three symbols, CR1 by the NYSE date (one cluster per event day).

## 3. Tests and decision rule

| test | events | gate |
|---|---|---|
| T1 | PRE-FOMC, pooled US500 / US30 / USTEC | BH over {T1, T2} at q = 0.10 on the one-sided p of excess z, AND mean net bp > 0 -> CANDIDATE |
| T2 | PRE-HOLIDAY, pooled | same |

- **Forward read (default):** ONE read, due when each run test has >= 40 event dates after the seal, or 5 years after the
  seal, whichever comes first (`edge_cal.forward_due`). It needs the index 5m history re-exported to a fixed end date.
- **History read (only under the owner override of §0):** ONE read over each symbol's first dense day -> 2026-09-25, read
  days excluded.
- Either way a pass is DISCOVERY-GRADE (too few events for a confirmation window). It earns a further forward stage, not a
  book slot.
- Without a sourced FOMC calendar file T1 is "not run (data)" and enters BH with p = 1 (T2's threshold stays 0.05).
- Zero candidates is a valid result.

## 4. Report-only (outside the family)

- Per symbol and per year, net at the p90 spread.
- Skipped events by reason (outside the span, read day by kind, no window, no null).

## 5. Windows: what has been read (strict)

- Forward event days: FRESH.
- History (override only): the remaining days are UNREAD-FOR-H (research-directions §0). The bars were read by census, F3,
  F4, F6 discovery, M1 discovery, AMD and Wyckoff L1; the G7 and M1 read days are excluded as above. The ledger states all
  CFD history is development (< 2024-03-01) or exposed (docs/architecture/research-ledger.json:148, :174).

## 6. Power and prior (before any read)

- Forward: FOMC 8 a year, pre-holiday 9-10 a year. 40 event dates per test take about 4-5 years. With a daily SD near 1 %,
  the SE of a mean over ~40 days is ~16 bp, so the MDE at 80 % power is ~40 bp per event.
- History under the override: ~39 pre-holiday and a similar fraction of FOMC days after the exclusions; the same MDE.
- Literature (not verified here): Lucca and Moench (2015, JF) report a large pre-FOMC drift in 1994-2011; later work
  reports it weakened after publication (candidates.md:43; crypto-cfd-design.md:248). Ariel (1990, JF) reports high
  pre-holiday returns; later work reports decay.
- Prior: ~10 % per test. Value if real is small: ~17 events a year, near-zero correlation with the gold book. CAL is cheap
  to seal now and to leave running; it is not a near-term lever.

## 7. Budget

- CAL: 2 tests, 1 read (forward by default). Shares a calendar build with NEWS-FLAT (research-directions §1.3).

## 8. Data

- **FOMC calendar (not in the repo).** Proposed path `data/history/calendars/fomc-scheduled.json`:
  `{"_source": [URLs], "_retrieved_utc": "...", "events": [{"date": "YYYY-MM-DD", "release_et": "HH:MM", "scheduled": true,
  "cancelled": false}]}`. Built by the coordinator from federalreserve.gov (the FOMC meeting-calendar pages), committed with
  its sha256 BEFORE the read. `edge_cal.load_fomc` refuses an unsourced file or a duplicate date. For the forward read, the
  file needs the dates published before each meeting (the Fed publishes a year ahead).
- Index 5m history and the NYSE calendar exist; the forward read needs a re-export through its end date.

## 9. Sealing steps (coordinator)

1. Review; record the owner's override decision in §0 (default NO). If YES, set `HISTORICAL_READ = True`.
2. Build and commit the FOMC calendar file.
3. Dry run (event and read-day counts only): `python3 scripts/research/edge_cal.py dry-run --fomc <file> --out <scratch>`.
4. Commit the final code; paste `python3 scripts/research/edge_cal.py manifest` into §10; seal under the final name with
   the exact "Status: SEALED" line; ledger note (CAL forward event days; or, under the override, the history read days).
5. Read once, committed alone:
   - forward: `python3 scripts/research/edge_cal.py run --read forward --fomc <file> --seal-date <seal> --end <last full
     server day> --out docs/audits/<date>-edge-cal-forward.json` (refused until due);
   - history (override only): `python3 scripts/research/edge_cal.py run --read history --fomc <file> --out ...`.

## 10. Code and its fingerprint

- `scripts/research/edge_cal.py`: `load_fomc`, `pre_holidays`, `m1_read_days`, `read_days`, `exit_clock`, `day_window`,
  `placebo`, `event_rows`, `verdicts`, `forward_due`, `dry_counts`, CLI with the registration guard and dataset snapshot.
- Reuses `scripts/research/edge_m1.py` (NYSE calendar, M1's read days), `scripts/research/edge_f4.py` (`tom_days`) and
  `scripts/research/edge_census.py` (Series, Costs, summarise, bh).
- Tests: `scripts/tests/test_edge_cal.py` (hand-built bars, synthetic calendar; read days skipped and kept out of the
  null; the history read refused without the override), `scripts/tests/test_prereg_guard.py`.
- The guard refuses a read unless every file in `edge_cal.CODE` is listed below with its current sha256, and refuses to
  write a result if the read executed a repository module not listed.

Code manifest (filled at sealing by `python3 scripts/research/edge_cal.py manifest`; empty in this draft):

```
(paste here)
```
