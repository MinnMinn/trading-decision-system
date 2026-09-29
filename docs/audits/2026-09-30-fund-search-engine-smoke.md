# fund-search engine smoke test (2026-09-30) — plumbing and feasibility, NOT an evaluation

Scope: `BtEngine.trades_for(baseline)` of `scripts/fund-search.py` on the real engine and real FTMO history
(`BT_HISTORY_ROOT=data/history/ftmo`, cutoff 2024-03-01), baseline (v1) values only, one symbol per run, real costs and
flat-before-rollover in the overlay. Output was restricted to structural facts: trade counts, dates, timings, invariants.
**No R, win rate or expectancy was printed, recorded or used to choose anything.** Nothing was sealed or declared.
Script: not committed (scratch); reproduce with `BtEngine(grid.runnable(), runner, tf, [symbol]).trades_for(grid.baseline())`.

## Plumbing (OBSERVED, all six runs)
- Trades exist; `beyond_cutoff` = 0; ADX(14) present on every trade; net-of-cost R is computed (`net_R` key present).
- `assert_no_rollover_crossing` (walked-bar basis) ran inside `trades_for` and did not trip on real history.
- `RUIN_FRAC` neutralised on the harness's own `bt` instance (0.0); `simulate` ran without post-ruin truncation.
- Wyckoff trades carry `volume_kind` = tick (CFD); ICT trades have none (expected).

## Baseline trade counts and timings (OBSERVED; single symbol, whole development span)
| Method | Symbol | TF | Trades | First entry | Elapsed |
|---|---|---|---|---|---|
| ICT | US500 | 30m | 13 | 2021-07 | 36 s |
| Wyckoff | US500 | 30m | 14 | 2021-03 | 15 s |
| ICT | US500 | 15m | 29 | 2021-07 | 84 s |
| Wyckoff | US500 | 15m | 33 | 2021-03 | 30 s |
| ICT | US500 | 5m | 80 | 2021-02 | 226 s |
| Wyckoff | US500 | 5m | 54 | 2021-03 | 84 s |
| ICT | XAUUSD | 15m | 103 | 2004-07 | 581 s |
| Wyckoff | XAUUSD | 15m | 148 | 2004-06 | 212 s |

## What this implies for the pre-registered rules (INFERRED, not tested)
1. **Frequency and sufficiency.** The plan requires >= 30 trades per 365-day test fold and a longest gap <= 30 days in
   >= 90 % of folds. XAUUSD 15m baseline is about 5 (ICT) and 7 (Wyckoff) trades a year per symbol; US500 30m is about 5
   a year. Pooling 2 metals or 5 indices lifts this only to roughly 10-15 (metals) or 25-50 (indices, 5m) a year, so
   most 15m/30m cells will read "insufficient" (never "pass") on the v1 baseline. This is the rule working as written,
   not a defect, and it may not be relaxed (plan §6.2: tighten only). V values that add trades (and the unadopted B-RAID,
   W2) change this; the baseline does not.
2. **Compute.** One ICT scan of XAUUSD 15m takes ~10 min. A cell needs about 41 (ICT) or 16 (Wyckoff) value sets plus the
   perturbation sets, per symbol. ICT metals 15m alone is on the order of 13 hours of scanning; 1m cells are ~15x more bars
   per year. The current workflow shards by cell only and a GitHub job is capped at 6 h, so the heaviest cells cannot finish
   as configured. Needs sharding by value set or symbol and/or the engine-speed work (branch `engine-speed`, scan cache).
3. The indices' usable history starts around 2021 even though the first bar is 2017-12, which shortens the number of
   usable folds for index cells (the 4-fold geometry printed by `plan` counts from the first bar).
