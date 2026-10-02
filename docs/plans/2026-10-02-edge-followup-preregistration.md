# Edge follow-up F2 -- pre-registration (2026-10-02, committed BEFORE any read of data at/after 2024-03-01 by this code)

Parent: docs/audits/2026-10-02-edge-census.md ("Next") and the owner's decision of 2026-10-02: stage (b) on the exposed window
to discard fast, then stage (a) forward paper/demo for whatever survives. Code: `scripts/research/edge_followup.py` (reuses
`scripts/research/edge_census.py` unchanged except the `end` parameter of `load`/`Series`); tests: `scripts/tests/test_edge_followup.py`.

## 1. What was decided from data already read (disclosed)

The census (development window, both its periods read) chose everything below: the three events, their directions, the five
symbols (by cost), and the idea of longer holds. This family is therefore NOT independent of the census; that is why its
confirmation cannot come from the development window.

| event | direction (relative to the census detector) | census basis |
|---|---|---|
| E1 prev-day sweep and close back inside | reversed = CONTINUATION in the sweep's direction | metals, significant in both census periods |
| E2 first close beyond the prev-day range | reversed = FADE | metals, significant in both census periods |
| E5 displacement-FVG retrace, filled at the edge | as detected = continuation | metals and indices, significant in both periods |

Symbols: XAUUSD, US30, DE40, USTEC, US500 (the five cheapest allowlisted CFDs, median round trip 0.43-0.83 bp). XAGUSD (4.4 bp),
FRA40 and AUS200 are out on cost.

## 2. Family

45 tests = 3 events x 5 symbols x 3 holds: 24 bars (2 h), 48 bars (4 h), `eod` (exit at the last 5m bar of the entry's server day,
i.e. flat before the broker rollover). Per symbol, not pooled. Everything else exactly as the census: signal on a closed bar,
entry next open (E5 at the edge), one event per (symbol, server day, event, side), excess over the same-window placebo (same
symbol, server minute-of-day, hold), real relative spread cost, CR1 by UTC date.

## 3. Stage (b): exposed window [2024-03-01, end of the exported data), read ONCE

This window is EXPOSED (prop-search 2024-03..2025-03 candidate selection; ADR 0008 after 2025-03), though none of these
primitives was ever measured on it. A test PASSES stage (b) iff, in its fixed direction:
1. Benjamini-Hochberg over the 45 ONE-sided p-values of the excess z rejects it at FDR q = 0.10;
2. its one-sided p < 0.05;
3. mean net return > 0 bp; and
4. mean net return under the p90 spread > 0 bp.

Per-year figures are report-only. A pass here is weak evidence (exposed window); a fail ENDS that test (it does not go to (a)).
Zero passes is a valid result and ends F2.

## 4. Stage (a): forward, on bars exported after this pre-registration

- Window: bars with time >= 2026-09-29T00:00:00Z (the stored exports end 2026-09-28), from new FTMO-Demo MT5 exports
  (`integrations/mt5/ExportHistory.mq5` -> `scripts/import-mt5-history.py`), the same code at the commit of this file.
- Only stage-(b) survivors are evaluated; each ONCE, when it first has >= 100 forward events or after 9 calendar months,
  whichever comes first.
- PASS iff mean net return > 0 bp and the excess z has a one-sided p < 0.10, Holm-adjusted over the survivors.
- A forward PASS makes the test a book COMPONENT (diagnosis §5 step 4); it then needs a trade rule with a stop, the FTMO
  policy simulation (step 5) and an execution comparison on demo before any challenge.

## 5. Not in scope

Changing any threshold after a read; adding symbols, events or holds without a new pre-registration; any execution.
