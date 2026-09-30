# ICT V items -- constants and choices to pre-register (DRAFT, UNSEALED)

Status: DRAFT. Not sealed, not a pre-registration. It lists every constant or interpretation the Batch 2(a) ICT V
items fixed where the plan (docs/plans/2026-09-28-methodology-improvement-plan.md §3) or the sources are silent, so
the owner can pre-register them BEFORE any evaluation. Declaration in code: `V_ICT` in scripts/ict-scan.py; grid file:
docs/architecture/v-grid-ict.json.

1. **ATR (B-BUF).** `ATR_PERIOD = 14`. ATR = simple mean of the true range (max of high-low, |high - prev close|,
   |low - prev close|; bar 0 = high-low) over the 14 bars ending at the MSS bar, inclusive; fewer bars near the window
   start. Buffer = 0.1 / 0.25 x ATR beyond the swept extreme (below for a long, above for a short).
2. **B-POOL.** Day boundary = UTC 00:00 (differs from the session registry's New York / London convention). Scope = the
   MOST RECENT completed UTC day (PDH/PDL) plus the MOST RECENT completed session of each of asia and london
   (sessions.json version 2 windows). Excluded: the still-forming day/session and the window-first partial
   day/session. A level shared with an existing pivot pool (same kind, within the equal-level tolerance) is not added
   twice.
3. **B-LB.** Lookback 12 = the live default (`max(12, recent*6)` at recent=2); 8 and 16 scale the live default by 8/12
   and 16/12 with `int(round())`. Effective bars: 15m/30m/1H/4H -> 8, 12, 16; 1m/5m (live default 24) -> 16, 24, 32.
   K = `bt.P[tf]["K"]`; 2K doubles it.
4. **B-EXIT time stop.** `1.5H = int(round(1.5 * H))`, `2H = 2 * H`, H = `bt.P[tf]["H"]`. `none` = no time exit: the trade
   runs to the end of history. **The fund cells must run with `flat_before_rollover=True` (no overnight holding is a
   fixed rule, plan §6 item 7); fund-search must ASSERT this**, because under `none` without it a position could be
   carried across many days.
5. **B-EXIT target.** Sigma projection from the leg: `origin +/- mult * leg`. -2.0 reads the existing `std["-2"]` entry
   (v1 number); -2.25 and -2.5 use the same formula at that multiple. Fallback when there is no leg to project from:
   the R15 dealing-range edge (unchanged).
6. **B-EXIT 2R (`no_floor`).** REMOVED FROM THE GRID 2026-09-30 (owner: planned R:R at entry must be at least 2.5R for
   every trade); the engine path remains but no grid cell can reach it. Skips simulate()'s planned-R:R ENTRY floor
   (`OPTS["min_rr"]`, 2.5 since 2026-09-30, was 2.0, net of fee) for ICT trades only. ICT trades are recognised by the event id form `<sym>-<side>-ict-<sweep>-<mss>`; Wyckoff ids
   (`<sym>-<side>-book-<t0>[-D]`) keep the floor. No profit-taking rule is added: "2R as profit-taking" is expressed only
   as the absence of the entry floor.
7. **B3.** Pairing table (entry -> bias TF) from models.md §2.8 TFA p5: 1m <- 15m, 5m <- 1H, 15m <- 4H, 1H <- 1D. Unpaired
   entry timeframes (30m, 2H, 4H, 1D) refuse every setup ("no pairing"). Gate keyed on the LTF bar's CLOSE.
8. **B7.** Windows = sessions.json version 2 (any window counts, Asia included; weekends gated), NOT core-a.md R1's
   literal 02:00-05:00 EST. Instrument set = asset_class `indices` only (metals never restricted). Instant = the fill
   bar's OPEN time (a proxy for the fill moment).
9. **B-PD r13.** Range = swept extreme (stop side, before any buffer) to the nearest unswept opposing pool beyond the
   entry; with no such pool the R15 edge on that side. Only the pd_ok range changes: the fallback TARGET edge stays the
   R15 range.
10. **B6.** Project rule (core-b.md R3 is the invalidation idea only). Window = bars `mss_i+1 .. fill_bar-1`; the fill bar
    itself is excluded (same-bar target and fill is unknowable from OHLC and keeps the fill).
11. **N accounting.** N = 1 + 27 + 1 = 29 per cell set (was 1 + 39 + 1 = 41 before `no_floor` was removed, 2026-09-30). B4 is counted while `implemented=false` (no key exists; the grid
    declares its two values). B3 is counted on the 30m cell although it produces no trades there (report "no pairing").
    B-EXIT counts as one factor of 12 value sets (was 24), B-LB as one of 6; B-DISP is sensitivity-only and not in N.
