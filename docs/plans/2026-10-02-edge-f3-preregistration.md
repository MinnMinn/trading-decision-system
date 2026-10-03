# Edge family F3 -- pre-registration (2026-10-02, committed BEFORE any run on real data)

Parent: owner approval 2026-10-02 ("Đồng ý đề xuất": a broader pre-registered family -- daily horizons, mean reversion after
large moves, a volatility-regime filter). Code: `scripts/research/edge_f3.py` (machinery from `scripts/research/edge_census.py`,
unchanged); tests: `scripts/tests/test_edge_f3.py` (synthetic bars only).

## 1. Hypotheses (all intraday: flat before the broker rollover, no swap)

| id | rule | hold |
|---|---|---|
| H1 | daily time-series momentum: sign of the previous 20 dense days' close-to-close return, traded from the day's first bar | to the last bar of the server day |
| H2 | daily shock reversal: previous day's return beyond 2 x its 20-day SD -> trade the opposite sign | server day |
| H3 | 1-hour shock fade: a 12-bar return beyond 3 x sigma_5m x sqrt(12) -> fade it (first per day per side) | 12 and 24 bars |
| H5 | E5 FVG retrace (census definition) only when the day's sigma_5m is above the median of the previous 250 dense days | 24 bars |
| H7 | first close beyond the previous day's high (low) when the 20-day momentum has the same sign | server day |

Disclosed origin: H5 comes from the gold reads of the census / F2 / the book design (the FVG retrace paid only in high-volatility
years); H7 combines E2 (read in the census) with H1. H1, H2, H3 have never been measured in this repository.

## 2. Universe and family

XAUUSD, US30, DE40, USTEC, US500 (the five cheapest allowlisted CFDs; cost is a fact, not an outcome). Per symbol.
FAMILY = 30 tests (H1, H2, H5, H7 x 5 symbols; H3 x 5 symbols x 2 holds).

## 3. Three reads, each once (dates only decide which bars belong where)

1. DISCOVERY = the first 60 % of the symbol's dense development days (< 2024-03-01), the census's own split day.
   Direction d = sign of the mean excess z. CANDIDATE iff Benjamini-Hochberg over the 30 two-sided p-values at q = 0.10
   rejects it AND the mean net return in direction d is > 0 bp.
2. CONFIRMATION = the last 40 % of the development days. CONFIRMED iff a candidate, and in direction d: one-sided p < 0.05,
   net > 0 bp, net under the p90 spread > 0 bp.
3. EXPOSED = 2024-03-01 -> end of the stored data (exposed by earlier selections, never by these hypotheses). SURVIVES iff
   confirmed, and in direction d: one-sided p < 0.10 and net > 0 bp.

Survivors go to the forward stage under the same rule as F2 (docs/plans/2026-10-02-edge-followup-preregistration.md §4) and,
if they pass it, into the book. Measurement exactly as the census: excess over the same-period, same-time-of-day, same-hold
placebo; relative spread cost; CR1 by UTC date. Zero survivors is a valid result.
