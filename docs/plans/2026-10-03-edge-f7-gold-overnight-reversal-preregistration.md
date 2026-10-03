# Edge family F7 -- overnight reversal after a US-session gold sell-off (XAUUSD) -- pre-registration

**Committed BEFORE any read of the F7 outcomes.** Same code and definitions as F6
(docs/plans/2026-10-03-edge-f6-overnight-reversal-preregistration.md §2): `scripts/research/edge_f6.py --family F7`.
Candidate B2 of docs/plans/2026-10-03-candidates.md.

## 1. Hypothesis

The immediacy / inventory premium behind F6 is not specific to equities (Grossman-Miller): if US-hours selling in gold is
absorbed by liquidity providers, gold should drift up overnight after a US-session sell-off. I know of NO gold-specific
published evidence; this is a TRANSFER test of a mechanism, with a lower prior than F6 and far more data (2004+). Direction
fixed: LONG; one-sided.

## 2. What differs from F6

- Symbol: XAUUSD. "US session" = the same New York 09:30-16:00 window (gold trades through it; COMEX floor hours differ, the
  window is kept identical to F6 so that the mechanism, not a window choice, is tested).
- Gold's FTMO day restarts at the server rollover like the indices; entry 19:00 New York, exits W1 (09:00 Berlin) and W2
  (09:30 New York) as in F6.
- **FAMILY F7 = 4 tests** = 2 thresholds {-0.5, -1.0} x 2 windows, with its OWN Benjamini-Hochberg at q = 0.10 (a separate
  family: another asset and another prior).
- Periods: discovery = first 60 % of XAUUSD's dense development days (split 2016-11-30), confirmation = the rest before
  2024-03-01, exposed = 2024-03-01 -> end. Same rules as F6 §3, incl. net > 0 at 2 x the median spread to confirm.

## 3. Prior reads (disclosed)

- F3 H2 on XAUUSD (fade the next whole server day after a +/-2 SD close-to-close day) was read in all three periods (positive
  but not significant nets). Its long-after-down-shock events overlap F7's theta = -1.0 days in part.
- AMD3 (development) showed that in New York hours gold CONTINUES a large excursion from the day's open; H7 / G9 trade that
  continuation intraday. F7 trades the opposite sign in the following night: if F7 survives, its correlation with H7 / G9 is
  expected to be <= 0 and must be measured (report-only, as in F6).

## 4. Power

~2,800 dense discovery days: an effect of ~2-3 bp per night is detectable. A null here is informative.
