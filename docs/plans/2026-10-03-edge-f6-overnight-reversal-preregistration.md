# Edge family F6 -- overnight reversal after a US cash-session sell-off (US indices) -- pre-registration

**Committed BEFORE any read of the F6 outcomes.** Code: `scripts/research/edge_f6.py --family F6`; tests:
`scripts/tests/test_edge_f6.py` (hand-built bars only, incl. the DST-asynchronous weeks). Candidate B1 of
docs/plans/2026-10-03-candidates.md; conditions (a)-(c) set by the debating session "Khám phá hệ thống FTMO" (reframes §9).

## 1. Hypothesis and source

After a US cash session that sold off, US index prices drift UP overnight as dealers who absorbed the selling unload it to
liquidity arriving in Asia and Europe; the effect is asymmetric (sell-offs reverse, rallies much less) and the unconditional
02:00-03:00 ET drift does NOT pay the bid-ask spread (Boyarchenko, Larsen, Whelan, "The Overnight Drift", RFS 36(9) 2023;
NY Fed Staff Report 917: Sharpe 1.1 gross -> -0.5 net for 02:00-03:00, 0.3 net for 01:30-03:30). Only the CONDITIONAL,
long-only version is tested. Direction fixed by the source: LONG; one-sided tests.

## 2. Definitions (all times by zoneinfo; FTMO server day = 17:00 -> 17:00 New York, all weeks)

- **Cash session** of New York date D: the 5m bars whose New York open time is in [09:30, 16:00) on D, inside server day D.
  Complete iff the 09:30 bar and the 15:55 bar exist and >= 70 of the 78 bars do. Session return r_s = C(15:55 bar) /
  O(09:30 bar) - 1.
- **Sell-off z**: z = r_s / SD of the previous 20 complete sessions' r_s (strictly earlier sessions; PIT).
- **Trigger** T(theta): z <= theta, theta in {-0.5, -1.0} (fixed now; no other threshold will be read).
- **Entry**: the next server day X' after the session's server day (the next one that has bars; Friday -> the Sunday-evening
  start of Monday's server day). Entry at the OPEN of the first bar of X' whose New York time is >= 19:00 on X''s starting
  New York date (one hour after the CME reopen, away from the reopen spread spike), and < 21:00 (else: data hole, skipped).
  The previous server day must be dense (`prev_dense`).
- **Exits**, the CLOSE of the last bar of X' that closes at or before: W1 = 09:00 Europe/Berlin on the next calendar
  morning (the European open the source names); W2 = 09:30 New York on the next morning (US cash open). Both are inside X'
  (it ends 17:00 New York). A window whose exit bar closes more than 30 min before its target is skipped (hole).
- **Return** r = C(exit) / O(entry) - 1 (bid bars), long.
- **Disclosed outcome-side filter** (found by the detector leakage probe before any read): a night counts only if its exit bar
  exists within 30 min of the target, so a night whose morning has a data hole is dropped. This can only drop events, never
  choose a different entry; the entry decision itself is point-in-time (`scripts/tests/test_detector_leakage_probe.py`).
- **Cost**: one relative spread per round trip, half at the entry UTC hour and half at the exit UTC hour, from the recorded
  hourly spreads (`ftmo_demo_2026_09_relspread`, a 2022-07..2026-09 recording per UTC hour, condition (a)). Stresses: p90
  spread, and 2 x the median spread.
- **Placebo (condition (c))**: the same window's mean r over the eligible NON-trigger days (z > theta) of the same symbol and
  period. excess = r - placebo. Scale for z units: sigma_5m x sqrt(bars held) (census definition).
- Statistics: `edge_census.summarise` (CR1 by date, one event per date per test).

## 3. Universe, family, reads

US500, US30, USTEC. **FAMILY F6 = 12 tests** = 3 symbols x 2 thresholds x 2 windows. Periods exactly as F3-F5: DISCOVERY =
first 60 % of the symbol's dense development days (< 2024-03-01; split days US500 2023-03-07, US30 2022-03-14, USTEC
2023-03-08), CONFIRMATION = the last 40 %, EXPOSED = 2024-03-01 -> end of data. Each read ONCE, in order, each in its own
commit.

1. DISCOVERY: CANDIDATE iff Benjamini-Hochberg over the 12 one-sided p-values of the excess z rejects it at q = 0.10 AND
   its mean net (median spread) > 0 bp.
2. CONFIRMATION: CONFIRMED iff a candidate and one-sided p < 0.05, net > 0, net at p90 > 0, AND net at 2 x median > 0
   (condition (a)(ii): an edge that does not clear twice the recorded spread is reported as "cost data insufficient", not
   as an edge).
3. EXPOSED: SURVIVES iff confirmed and one-sided p < 0.10, net > 0.

Report-only at every read: the UNCONDITIONAL window (all eligible days) net bp and its t against zero (the seasonal null of
reframes R6a); n and the minimum detectable mean (80 % power, one-sided alpha 0.10); the daily-P&L correlation of each test
with the point-in-time base book (H7 + G9 gold) and with v2 as executed, on that read's dates (condition: "low" must become
a number).

## 4. Prior reads (disclosed)

- F3 H2 (daily shock reversal: previous day's close-to-close return beyond 2 SD -> fade the whole next server day, both
  directions) was read on US30, USTEC, US500 in all three periods. Its long events overlap F6's theta = -1.0 trigger days in
  part (different return definition, different window, both sides). F6's window and asymmetry come from the 2020 paper,
  not from H2; the overlap still weakens F6's confirmation and exposed reads as independent evidence.
- Census E3 / E4 (Asia-range events, 00-07 UTC range, 07-16 UTC signals), E7 (last-30-min momentum) and AMD (session
  profiles) used other triggers and windows on the same bars.
- The hourly spread table was printed for US500 / US30 / USTEC / DE40 / XAUUSD before this file (a cost fact, not an
  outcome; it chose the 19:00 New York entry away from the reopen hour).

## 5. Power, honestly

Discovery holds ~380 dense days on US500 / USTEC (~60-130 trigger days) and ~760 on US30. At an overnight-window SD of tens of
bp, only an effect of several bp per night is detectable. "Not found" here will mean "not found at this power", reported with
its minimum detectable effect.

## 6. After the reads

A survivor becomes a book component candidate: protective stop, FTMO replay with the base, the value objective at edge x
{1, 0.5, 0}, and execution parity on demo before any challenge. Zero survivors is a valid result.
