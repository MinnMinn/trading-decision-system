# Edge family F5 -- pre-registration (2026-10-02, committed BEFORE any run on real data)

Parent: docs/audits/2026-10-02-edge-f4.md §3 -- the book's binding constraint is FACTOR DIVERSITY (every robust edge so far is
metals intraday trend continuation, plus E5 US500). Owner goal: "Pass FTMO bằng bất kỳ phương pháp nào đã kiểm chứng". Code:
`scripts/research/edge_f5.py`; tests: `scripts/tests/test_edge_f5.py`.

## 1. Hypotheses = TRANSFER of the surviving rule types, unchanged

| rule | definition (unchanged code) | hold |
|---|---|---|
| E5 | FVG retrace (edge_census.ev_fvg) | metals 24 bars (as XAUUSD), indices 48 bars (as US500) |
| H7 | prev-day breakout with the 20-day momentum (edge_f3.ev_breakout_trend) | to the end of the server day |
| G9 | volatility breakout, open +/- 0.5 x previous range (edge_f4.ev_vol_breakout) | to the end of the server day |

Symbols: the nine RESEARCH-ONLY symbols (instruments.json `research_only`), none of whose returns any edge family (census, F2,
F3, F4) has read: XPTUSD, XPDUSD, JP225, HK50, UK100, EU50, US2000, SPN35, N25. (Their trade COUNTS were used by the
2026-10-01 cell-selection power work; no return was read.) FAMILY = 27 tests.

Direction is FIXED in advance: +1 (the rule's own sign, the sign in which it survived). All p-values one-sided.

## 2. Three reads, each once

1. DISCOVERY = first 60 % of the symbol's dense development days (< 2024-03-01). CANDIDATE iff BH over the 27 one-sided
   p-values at q = 0.10 rejects AND net > 0 bp.
2. CONFIRMATION = last 40 % of development days: one-sided p < 0.05, net > 0, net at the p90 spread > 0.
3. HOLDOUT = 2024-03-01 -> end of data (never read for these symbols, so a true holdout here): one-sided p < 0.10, net > 0.

Measurement exactly as F3 (excess over same-period / same-time-of-day / same-hold placebo; relative spread cost; CR1 by UTC
date). Signals on a day's last bar are dropped (no same-day trade). Zero survivors is a valid result.

## 3. After the reads

Survivors are evaluated as book components against docs/architecture/book-baseline.json with `book_sim.py compare` (same span,
vol-matched risk, correlation with the baseline). A survivor can reach the demo executor only after (i) the owner moves the
symbol from research-only to the execution allowlist and (ii) the forward stage (a) per
docs/plans/2026-10-02-edge-followup-preregistration.md §4.
