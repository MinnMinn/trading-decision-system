# FVG-retrace book: full-history stability, trade-rule design and FTMO replay (2026-10-02)

DESIGN on already-read history (owner 2026-10-02): nothing here validates the components; the forward stage (a) of
docs/plans/2026-10-02-edge-followup-preregistration.md does. Raw: `docs/audits/2026-10-02-edge-followup-history.json`
(`edge_followup.py run --stage history`, report-only) and `docs/audits/2026-10-02-fvg-book-sim.json` (`scripts/research/fvg_book_sim.py`).

## 1. Per-year stability over every stored year (report-only)

| component | span | net bp (all) | positive net years | note |
|---|---|---|---|---|
| E5 XAUUSD, hold 2 h | 2004-2026 | +0.35 | 14 of 23 | the gross excess is positive almost every year, but it nets ~0 in 2008-2020; the net edge is a 2021-26 (and 2006) phenomenon |
| E5 US500, hold 4 h | 2021-2026 | +0.59 | 6 of 6 | consistent but small, and only six years of dense data |

The gold component is REGIME-DEPENDENT: the signal is persistent, the profit is not -- it needs moves large relative to the spread.

## 2. Trade rule (two stop rules fixed before looking)

| component, stop | trades | mean R | stopped out | median stop | reading |
|---|---|---|---|---|---|
| XAUUSD, `far_edge` (gap far edge, the ICT source's "FVG end") | 10257 | **-0.44** | 80 % | 3.0 bp | the source stop is inside the spread noise: dead |
| US500, `far_edge` | 2536 | **-0.23** | 84 % | 2.2 bp | dead |
| XAUUSD, `sigma2` (2 sigma of the hold) | 10329 | +0.004 | 1.7 % | 64 bp | effectively a time-exit trade |
| US500, `sigma2` | 2547 | +0.009 | 0.9 % | 71 bp | effectively a time-exit trade |

The tight "textbook" stop turns a positive time-exit edge into a large loss -- the same mechanism the diagnosis found for the
full ICT/Wyckoff setups (§3: stops of a few bp, costs that are a large fraction of them).

## 3. FTMO replay on the real trade sequence (challenge started every Monday, no bootstrap)

`sigma2` stop. "Unlimited" = FTMO's own rule (no time limit); "120 d" = passed within 120 weekdays.

| book, risk/trade | Phase 1 within 120 d | Phase 1 unlimited | median days to pass | fail | Phase 2 unlimited |
|---|---|---|---|---|---|
| XAUUSD + US500 (2021-26), 1 % | 0.24 | **0.90** | 288 | 0.8 % | 0.93 |
| XAUUSD + US500 (2021-26), 0.5 % | 0.02 | 0.83 | 730 | 0 % | 0.91 |
| XAUUSD alone (2004-26), 1 % | 0.04 | 0.55 | 527 | 43 % | 0.68 |

Pass rate by start year, XAUUSD alone at 1 %: 2004-07 ~1.0, **2008-2016 0.0-0.12** (and 0.49 in 2012), 2017-19 0.48-0.96,
2020-25 1.0. The two-component book exists only from 2021 (US500 dense data), i.e. only in the favourable regime.

## 4. Reading

- In-sample, the shape is viable for FTMO's no-time-limit rules: low failure (the 2-sigma stop is rarely hit, so a day rarely
  loses much) and a slow drift to the target -- about 10 months median at 1 % risk. That is a slow, low-variance grind, not a
  fast challenge.
- It is NOT robust: the same component lost the whole 2008-2016 period, and the book has never been observed outside the
  2021-26 regime. The forward stage must therefore also watch the regime; a period like 2008-16 would show up as a flat or
  negative forward mean, and the pre-registered stage-(a) rule would end it.
- Honest expectation: these two components are the best evidence this repository has produced, and they are thin. A robust
  FTMO book needs more independent components; the census family was small (8 events). Widening the search -- new
  pre-registered families, other horizons (daily), other primitives -- is the next research step, in parallel with stage (a).

## 5. Forward paper log (stage (a) data, PAPER ONLY)

`scripts/research/fvg_forward.py scan | resolve | status`: logs every forward E5 signal (entry >= 2026-09-29) for both
components with the `sigma2` stop and time exit, from the stored history merged with the live MT5 bridge 5m file. It places
no order. Run `scan` and `resolve` a few times a day (or from the existing automation), re-export the 5m history at least every
3 weeks (a signal with stale volatility history is logged as REFUSED). `status` says when stage (a) is due (100 closed events
or 9 months); the stage-(a) verdict itself is `edge_followup.py run --stage forward --since 2026-09-29T00:00:00Z`.
Demo ORDERS (the paired execution comparison) are not wired: that is a change to the execution path (CLAUDE.md §51, the
pilot is OFF by owner decision) and needs its own approval.
