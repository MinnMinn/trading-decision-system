# E5 live-fill re-simulation -- pre-registration (2026-10-03, committed BEFORE the run)

**Status: DESCRIPTIVE / EXPOSED.** Every bar used here was already read to select and design E5 (census, F2 history,
fvg-book-sim, book-sim, pass-policy). This is a validity check of an EXISTING component's execution model, not a search and
not new evidence of edge. Agreed as "Test #1" by both debating sessions (docs/plans/2026-10-03-reframes.md §9, round A).
Code: `scripts/research/e5_live_fill.py`; tests: `scripts/tests/test_e5_live_fill.py` (hand-built bars only).

## 1. Question

The research fills an E5 LONG when the BID bar's low touches the gap's near edge (`edge_census.py:276`, price
min(edge, open)) and charges one spread on top. The demo places a BUY LIMIT at the same bid-derived edge
(`fvg_demo.py:387`); MT5 triggers a buy limit on the ASK, so it fills only when bid <= edge - spread. Shorts are consistent
(a sell limit triggers on the bid). Does the E5 long population that the live order actually trades carry the edge the book
was designed on, and what does the v2 book look like when E5 longs are simulated as executed?

## 2. Fill rules (longs; shorts use the research rule in every variant)

`sp_j` = the median relative spread recorded for bar j's UTC hour (`ftmo_demo_2026_09_relspread`) x price x `sx`, the ask path
approximated as bid + sp_j over the whole bar (disclosed: a spread spike at the touch is not modelled; it would only remove
live fills).

| rule | fill condition on bar j | entry price | cost |
|---|---|---|---|
| `research` | L_j <= edge | min(edge, O_j) (bid terms) | one spread, half at the entry hour, half at the exit hour (as book_sim) |
| `live` (v2 as coded) | L_j + sp_j <= edge | min(edge, O_j + sp_j) (ASK) | none on top: the ask was paid, the exit is at the bid |
| `plus_spread` (candidate v3 fix) | L_j + sp_j <= edge + sp_p | min(edge + sp_p, O_j + sp_j) (ASK) | none on top |

`sp_p` = the spread at the placement hour (the bar after the gap's third bar). `plus_spread` reproduces the research
population with an order the broker can actually execute. Everything else is book_sim's trade mechanics unchanged: touch
window 24 bars inside the gap's server day, protective stop 2 x sigma_5m x sqrt(hold) from the entry price, time exit (24
bars XAUUSD, 48 bars US500), flat before the rollover, R = net P&L / stop distance. Selection: the first FILLED gap per
(symbol, server day, side), as the demo executor (`fvg_demo.py` cancels siblings on the first fill); the book_sim reference
(first gap per day in formation order) is reported next to it so the selection change can be seen separately.

Spread sensitivity (the snapshot is one 2022-07..2026-09 recording, reframes R6e): sx = 0.5, 1, 2.

## 3. Outputs (all reported, none tuned)

1. Per component (E5 XAUUSD 24, E5 US500 48) x side x rule x sx: gaps eligible, fills, fill rate, mean R, sd R, mean net bp,
   per-year mean R, on the full history and on the book span (from 2021-10-12).
2. The v2 book (H7 XAUUSD + G9 XAUUSD + E5 XAUUSD + E5 US500, 1 %, dd3, no day stop) with E5 under each rule at sx = 1,
   through `scripts/research/pass_policy.py`'s own functions: selection starts (< 2024), confirmation starts (>= 2024), and
   the stationary block bootstrap at the edge as measured and with the 50 % haircut; floating P&L as FTMO counts it
   (`mae`, the upper bound) and realised.
3. Daily Sharpe of each book variant (book_sim.daily_profile).

## 4. How the result is read (fixed now)

- If `live` E5-long mean R <= 0 on the book span at sx = 1: E5 longs as executed by v2 have no supporting evidence; the v2
  book with `live` longs becomes the honest baseline in every later comparison.
- If `plus_spread` beats `live` on mean R on the book span AND on the full history at sx = 1: recommend to the owner a v3
  executor that places the long limit at edge + current spread (version-significant, CLAUDE.md §47; owner decision).
- If `live` beats `plus_spread` on both: the executor's order is the better one and the research numbers understate E5 longs;
  reported as such.
- Mixed: reported as mixed; no recommendation.

Nothing here changes the demo, a Trading System version, a config or an account. The research ledger is not updated (no new
period is exposed).
