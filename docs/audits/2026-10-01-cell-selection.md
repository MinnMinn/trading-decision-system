# Cell selection for the enlarged symbol sets (2026-10-01): trade counts + power model + pre-stated rule

Status: MODEL + COUNTS ONLY. Only admitted-trade COUNTS, bar counts and seconds were measured; the power model runs on synthetic binary
(+2.5R / -1R) outcomes. No performance figure of any kind was read from any data (grep of this note, the script, the JSON artefacts and the run
logs for the performance terms returned 0 hits). Nothing is declared, evaluated or sealed; no harness, engine, threshold or cells-file edit.
Branch `b16-cell-selection` from `windows-migration` bf69cc0.

## 1. The rule and its disclosed post-hoc element
Pre-stated (owner approved BEFORE these measurements): a cell is INCLUDED iff `e_min <= k * e_star` for at least one of {ICT, WYCKOFF-BOOK}, k = 2.
- `e_min` = smallest net edge (R/trade, binary +2.5/-1, cost 0.07R) at which the harness's own lower-bound rule (`fund_stats.robust_lower_bound`: iid t,
  date / 30-day / quarter / half-year CR1 bounds, at the N-adjusted confidence, pass = bound > 0) has power >= 0.80. Reported as the first GRID value
  (grid 0.025 steps from 0.05 to 0.40, then 0.50, 0.60, 0.80, 1.00) and, for information, a linear interpolation. The verdict uses the grid value.
- `e_star` = smallest net edge with `prop_pass_probability >= 0.70` on the binding fund (max over ftmo-challenge-phase1 and the5ers-high-stakes-step1),
  via prop-search's own FUNDS / horizon / account profiles (`power_model.run_prop`, 9-step bisection, 20000-trade population stream).
- **k = 2 was chosen after the earlier ratios (docs/audits/2026-10-01-power-model.md) had been seen.** It is a post-hoc threshold, not a
  pre-registered one. Section 5 shows k in {1.5, 2, 2.5, 3}; the set changes between k = 2 and k = 2.5 (15m-metals), so the choice matters.

## 2. Inputs and what was measured
- Counts: `scripts/research/trade_rates.py` extended minimally (`--symbols`, `--tfs` for `run` / `coverage`; no engine or harness change): the 10 new symbols
  (XPTUSD XPDUSD UK100 EU50 JP225 HK50 AUS200 US2000 SPN35 N25) at 5m, 15m, 30m and the 7 old symbols at 30m, both methods, slices S1-S3 =
  222 jobs, all status OK, 4 concurrent in-process processes, longest job 122 s. Old symbols at 5m/15m and the 1m cells reuse b10's published numbers
  (`docs/audits/2026-10-01-trade-rates.md`; the 1m cells use b10's published pooled rate unchanged, with 2 / 5 symbols).
- Rate per symbol = mean over its COMPLETE slices only (in-slice bars >= 90 % of its best slice; same rule as b10). Pooled cell rate = SUM of per-symbol
  rates. Raw data: `docs/audits/2026-10-01-cell-selection-counts.jsonl` (the 222 job results) and `-rates.json` (per-symbol counts, completeness, first bars).
- Folds: `plan --dry-run`: 1m-metals 9, 1m-indices 4, 5m/15m-metals 17, 5m/15m-indices 4. 30m cells derived with `fund_stats.make_folds` from the earliest
  symbol's first 30m bar (XAUUSD 2004-06-11 gives 17; DE40 2017-12-27 gives 4): verified.
- First bars (identical at 5m/15m/30m): XAUUSD 2004-06-11, XAGUSD 2008-11-07, XPTUSD/XPDUSD 2015-01-06, DE40 2017-12-27, US500/USTEC/FRA40/UK100/EU50/JP225
  2017-12-28, US2000 2018-01-23, HK50 2018-12-16, US30/AUS200 2019-02-08 (as loaded by the harness, PIT-cut), SPN35 2020-11-08, N25 2020-11-11.
- Power model: `scripts/research/power_model.py` imported and called. Only change: `gen_stream` takes an optional per-symbol rate vector and an optional
  `sym_first_day` (defaults reproduce the original streams bit for bit; a re-run of the stored job `main|ICT|15m-metals` at e = 0.30 gave the identical
  0.71 / 0.745 / 0.765 / 0.80 / 0.82). Base assumptions as in the existing doc: sigma 0.75, tau 0.03, rho 0.3, c 0.07R, 200 replications per cell and e
  (Monte-Carlo SE <= 0.035), seeds from crc32(label) + 20261001.

## 3. Pooling variants (what "the cell's trade rate" means)
The brief asks for pooled rates under an effective-symbol discount (base rho 0.3). Formula used (mine, not the power model's): k_eff = k / (1 + (k-1) rho),
pooled_eff = sum x k_eff / k. The primary variant was fixed BEFORE any power result was seen:
- **base (PRIMARY, used for the recommendation)**: discounted rate at rho 0.3 AND simulated regime correlation rho 0.3. This counts the correlation twice
  (once as lost trades, once as correlated regimes in the simulation), so it is conservative; for 13 symbols k_eff is only 2.83 (the discount removes about 78 %
  of the sum).
- sum03: undiscounted SUM rate with regime rho 0.3 (the power model's own mechanism only). Optimistic bound.
- rho0: sum rate, rho 0. rho06: rate discounted at 0.6, regime rho 0.6.
- avail: base rates, but each late symbol has no trades before its first bar (per-symbol rates; folds as in the plan). The existing power model (and the
  base variant) assume every symbol trades in every fold; for the metals cells XAGUSD (2008-11) and XPT/XPD (2015-01) do not exist in the early folds, so
  base overstates the metals pooled test trades.
e_star always uses the variant's pooled rate (for avail: the base rate) with the 120-day challenge horizon.

## 4. Results (generated by `scripts/research/cell_selection.py report`)

### T1. Per-symbol admitted trades per one-year slice and per-symbol yearly rate (counts only)

S1/S2/S3 = 2021-03-01..2022-03-01 / ..2023-03-01 / ..2024-03-01. `*` = slice partly uncovered (bars < 90 % of the symbol's best slice; excluded from the rate). rate = mean over the complete slices. source b10 = docs/audits/2026-10-01-trade-rates.md, b16 = this run.

| method | tf | symbol | S1 | S2 | S3 | slices used | rate /yr | source | first bar (run) |
|---|---|---|---|---|---|---|---|---|---|
| ICT | 5m | XAUUSD | 44 | 61 | 57 | S1,S2,S3 | 54.0 | b10 |  |
| ICT | 5m | XAGUSD | 52 | 66 | 57 | S1,S2,S3 | 58.3 | b10 |  |
| ICT | 5m | XPTUSD | 35 | 33 | 31 | S1,S2,S3 | 33.0 | b16 | 2015-01-06 |
| ICT | 5m | XPDUSD | 50 | 72 | 34 | S1,S2,S3 | 52.0 | b16 | 2015-01-06 |
| ICT | 5m | US500 | 30* | 59 | 72 | S2,S3 | 65.5 | b10 |  |
| ICT | 5m | US30 | 62 | 65 | 76 | S1,S2,S3 | 67.7 | b10 |  |
| ICT | 5m | USTEC | 23* | 69 | 88 | S2,S3 | 78.5 | b10 |  |
| ICT | 5m | DE40 | 14* | 69 | 71 | S2,S3 | 70.0 | b10 |  |
| ICT | 5m | FRA40 | 34* | 56 | 45 | S2,S3 | 50.5 | b10 |  |
| ICT | 5m | UK100 | 32* | 72 | 55 | S2,S3 | 63.5 | b16 | 2017-12-28 |
| ICT | 5m | EU50 | 31* | 49 | 35 | S2,S3 | 42.0 | b16 | 2017-12-28 |
| ICT | 5m | JP225 | 34* | 71 | 56 | S2,S3 | 63.5 | b16 | 2017-12-28 |
| ICT | 5m | HK50 | 25* | 49 | 56 | S2,S3 | 52.5 | b16 | 2018-12-16 |
| ICT | 5m | AUS200 | 59 | 51 | 62 | S1,S2,S3 | 57.3 | b16 | 2019-02-08 |
| ICT | 5m | US2000 | 68 | 59 | 66 | S1,S2,S3 | 64.3 | b16 | 2018-01-23 |
| ICT | 5m | SPN35 | 19* | 20 | 31 | S2,S3 | 25.5 | b16 | 2020-11-08 |
| ICT | 5m | N25 | 26 | 5* | 6* | S1 | 26.0 | b16 | 2020-11-11 |
| ICT | 15m | XAUUSD | 12 | 18 | 15 | S1,S2,S3 | 15.0 | b10 |  |
| ICT | 15m | XAGUSD | 18 | 20 | 23 | S1,S2,S3 | 20.3 | b10 |  |
| ICT | 15m | XPTUSD | 13 | 13 | 11 | S1,S2,S3 | 12.3 | b16 | 2015-01-06 |
| ICT | 15m | XPDUSD | 14 | 17 | 12 | S1,S2,S3 | 14.3 | b16 | 2015-01-06 |
| ICT | 15m | US500 | 14* | 18 | 21 | S2,S3 | 19.5 | b10 |  |
| ICT | 15m | US30 | 18 | 16 | 24 | S1,S2,S3 | 19.3 | b10 |  |
| ICT | 15m | USTEC | 17* | 23 | 14 | S2,S3 | 18.5 | b10 |  |
| ICT | 15m | DE40 | 6* | 24 | 22 | S2,S3 | 23.0 | b10 |  |
| ICT | 15m | FRA40 | 17* | 15 | 23 | S2,S3 | 19.0 | b10 |  |
| ICT | 15m | UK100 | 16* | 22 | 14 | S2,S3 | 18.0 | b16 | 2017-12-28 |
| ICT | 15m | EU50 | 12* | 16 | 25 | S2,S3 | 20.5 | b16 | 2017-12-28 |
| ICT | 15m | JP225 | 8* | 24 | 15 | S2,S3 | 19.5 | b16 | 2017-12-28 |
| ICT | 15m | HK50 | 13* | 24 | 18 | S2,S3 | 21.0 | b16 | 2018-12-16 |
| ICT | 15m | AUS200 | 15 | 21 | 20 | S1,S2,S3 | 18.7 | b16 | 2019-02-08 |
| ICT | 15m | US2000 | 19 | 24 | 15 | S1,S2,S3 | 19.3 | b16 | 2018-01-23 |
| ICT | 15m | SPN35 | 12* | 14 | 12 | S2,S3 | 13.0 | b16 | 2020-11-08 |
| ICT | 15m | N25 | 6 | 2* | 0* | S1 | 6.0 | b16 | 2020-11-11 |
| ICT | 30m | XAUUSD | 1 | 11 | 7 | S1,S2,S3 | 6.3 | b16 | 2004-06-11 |
| ICT | 30m | XAGUSD | 2 | 8 | 8 | S1,S2,S3 | 6.0 | b16 | 2008-11-07 |
| ICT | 30m | XPTUSD | 1 | 3 | 11 | S1,S2,S3 | 5.0 | b16 | 2015-01-06 |
| ICT | 30m | XPDUSD | 3 | 9 | 4 | S1,S2,S3 | 5.3 | b16 | 2015-01-06 |
| ICT | 30m | US500 | 9* | 11 | 9 | S2,S3 | 10.0 | b16 | 2017-12-28 |
| ICT | 30m | US30 | 9 | 17 | 13 | S1,S2,S3 | 13.0 | b16 | 2019-02-08 |
| ICT | 30m | USTEC | 12* | 10 | 15 | S2,S3 | 12.5 | b16 | 2017-12-28 |
| ICT | 30m | DE40 | 1* | 6 | 9 | S2,S3 | 7.5 | b16 | 2017-12-27 |
| ICT | 30m | FRA40 | 11* | 14 | 4 | S2,S3 | 9.0 | b16 | 2017-12-28 |
| ICT | 30m | UK100 | 17* | 8 | 5 | S2,S3 | 6.5 | b16 | 2017-12-28 |
| ICT | 30m | EU50 | 4* | 10 | 15 | S2,S3 | 12.5 | b16 | 2017-12-28 |
| ICT | 30m | JP225 | 8* | 7 | 5 | S2,S3 | 6.0 | b16 | 2017-12-28 |
| ICT | 30m | HK50 | 4* | 7 | 8 | S2,S3 | 7.5 | b16 | 2018-12-16 |
| ICT | 30m | AUS200 | 5 | 7 | 6 | S1,S2,S3 | 6.0 | b16 | 2019-02-08 |
| ICT | 30m | US2000 | 10 | 15 | 15 | S1,S2,S3 | 13.3 | b16 | 2018-01-23 |
| ICT | 30m | SPN35 | 6* | 10 | 3 | S2,S3 | 6.5 | b16 | 2020-11-08 |
| ICT | 30m | N25 | 2 | 0* | 2* | S1 | 2.0 | b16 | 2020-11-11 |
| WYCKOFF | 5m | XAUUSD | 52 | 58 | 63 | S1,S2,S3 | 57.7 | b10 |  |
| WYCKOFF | 5m | XAGUSD | 43 | 62 | 60 | S1,S2,S3 | 55.0 | b10 |  |
| WYCKOFF | 5m | XPTUSD | 36 | 62 | 39 | S1,S2,S3 | 45.7 | b16 | 2015-01-06 |
| WYCKOFF | 5m | XPDUSD | 31 | 46 | 48 | S1,S2,S3 | 41.7 | b16 | 2015-01-06 |
| WYCKOFF | 5m | US500 | 26* | 62 | 51 | S2,S3 | 56.5 | b10 |  |
| WYCKOFF | 5m | US30 | 53 | 63 | 54 | S1,S2,S3 | 56.7 | b10 |  |
| WYCKOFF | 5m | USTEC | 31* | 61 | 40 | S2,S3 | 50.5 | b10 |  |
| WYCKOFF | 5m | DE40 | 7* | 49 | 51 | S2,S3 | 50.0 | b10 |  |
| WYCKOFF | 5m | FRA40 | 24* | 49 | 35 | S2,S3 | 42.0 | b10 |  |
| WYCKOFF | 5m | UK100 | 24* | 42 | 56 | S2,S3 | 49.0 | b16 | 2017-12-28 |
| WYCKOFF | 5m | EU50 | 18* | 59 | 41 | S2,S3 | 50.0 | b16 | 2017-12-28 |
| WYCKOFF | 5m | JP225 | 29* | 42 | 44 | S2,S3 | 43.0 | b16 | 2017-12-28 |
| WYCKOFF | 5m | HK50 | 19* | 36 | 45 | S2,S3 | 40.5 | b16 | 2018-12-16 |
| WYCKOFF | 5m | AUS200 | 46 | 64 | 44 | S1,S2,S3 | 51.3 | b16 | 2019-02-08 |
| WYCKOFF | 5m | US2000 | 61 | 43 | 47 | S1,S2,S3 | 50.3 | b16 | 2018-01-23 |
| WYCKOFF | 5m | SPN35 | 11* | 28 | 30 | S2,S3 | 29.0 | b16 | 2020-11-08 |
| WYCKOFF | 5m | N25 | 21 | 7* | 6* | S1 | 21.0 | b16 | 2020-11-11 |
| WYCKOFF | 15m | XAUUSD | 25 | 22 | 19 | S1,S2,S3 | 22.0 | b10 |  |
| WYCKOFF | 15m | XAGUSD | 25 | 24 | 21 | S1,S2,S3 | 23.3 | b10 |  |
| WYCKOFF | 15m | XPTUSD | 23 | 21 | 19 | S1,S2,S3 | 21.0 | b16 | 2015-01-06 |
| WYCKOFF | 15m | XPDUSD | 19 | 20 | 7 | S1,S2,S3 | 15.3 | b16 | 2015-01-06 |
| WYCKOFF | 15m | US500 | 11* | 21 | 19 | S2,S3 | 20.0 | b10 |  |
| WYCKOFF | 15m | US30 | 22 | 23 | 19 | S1,S2,S3 | 21.3 | b10 |  |
| WYCKOFF | 15m | USTEC | 5* | 20 | 26 | S2,S3 | 23.0 | b10 |  |
| WYCKOFF | 15m | DE40 | 5* | 18 | 16 | S2,S3 | 17.0 | b10 |  |
| WYCKOFF | 15m | FRA40 | 8* | 12 | 11 | S2,S3 | 11.5 | b10 |  |
| WYCKOFF | 15m | UK100 | 7* | 17 | 17 | S2,S3 | 17.0 | b16 | 2017-12-28 |
| WYCKOFF | 15m | EU50 | 3* | 13 | 18 | S2,S3 | 15.5 | b16 | 2017-12-28 |
| WYCKOFF | 15m | JP225 | 15* | 10 | 23 | S2,S3 | 16.5 | b16 | 2017-12-28 |
| WYCKOFF | 15m | HK50 | 6* | 19 | 16 | S2,S3 | 17.5 | b16 | 2018-12-16 |
| WYCKOFF | 15m | AUS200 | 21 | 17 | 20 | S1,S2,S3 | 19.3 | b16 | 2019-02-08 |
| WYCKOFF | 15m | US2000 | 18 | 13 | 20 | S1,S2,S3 | 17.0 | b16 | 2018-01-23 |
| WYCKOFF | 15m | SPN35 | 6* | 10 | 11 | S2,S3 | 10.5 | b16 | 2020-11-08 |
| WYCKOFF | 15m | N25 | 9 | 3* | 2* | S1 | 9.0 | b16 | 2020-11-11 |
| WYCKOFF | 30m | XAUUSD | 10 | 5 | 3 | S1,S2,S3 | 6.0 | b16 | 2004-06-11 |
| WYCKOFF | 30m | XAGUSD | 5 | 4 | 5 | S1,S2,S3 | 4.7 | b16 | 2008-11-07 |
| WYCKOFF | 30m | XPTUSD | 6 | 6 | 4 | S1,S2,S3 | 5.3 | b16 | 2015-01-06 |
| WYCKOFF | 30m | XPDUSD | 2 | 3 | 6 | S1,S2,S3 | 3.7 | b16 | 2015-01-06 |
| WYCKOFF | 30m | US500 | 4* | 2 | 3 | S2,S3 | 2.5 | b16 | 2017-12-28 |
| WYCKOFF | 30m | US30 | 3 | 3 | 4 | S1,S2,S3 | 3.3 | b16 | 2019-02-08 |
| WYCKOFF | 30m | USTEC | 3* | 4 | 6 | S2,S3 | 5.0 | b16 | 2017-12-28 |
| WYCKOFF | 30m | DE40 | 0* | 6 | 5 | S2,S3 | 5.5 | b16 | 2017-12-27 |
| WYCKOFF | 30m | FRA40 | 1* | 7 | 5 | S2,S3 | 6.0 | b16 | 2017-12-28 |
| WYCKOFF | 30m | UK100 | 1* | 10 | 2 | S2,S3 | 6.0 | b16 | 2017-12-28 |
| WYCKOFF | 30m | EU50 | 2* | 5 | 2 | S2,S3 | 3.5 | b16 | 2017-12-28 |
| WYCKOFF | 30m | JP225 | 2* | 7 | 8 | S2,S3 | 7.5 | b16 | 2017-12-28 |
| WYCKOFF | 30m | HK50 | 2* | 3 | 3 | S2,S3 | 3.0 | b16 | 2018-12-16 |
| WYCKOFF | 30m | AUS200 | 6 | 3 | 5 | S1,S2,S3 | 4.7 | b16 | 2019-02-08 |
| WYCKOFF | 30m | US2000 | 3 | 2 | 4 | S1,S2,S3 | 3.0 | b16 | 2018-01-23 |
| WYCKOFF | 30m | SPN35 | 1* | 2 | 4 | S2,S3 | 3.0 | b16 | 2020-11-08 |
| WYCKOFF | 30m | N25 | 2 | 0* | 1* | S1 | 2.0 | b16 | 2020-11-11 |

### T2. Pooled trade rate per candidate cell (trades / year, sum over symbols) and effective-symbol discount

sum = SUM of per-symbol rates (1m cells: b10's published pooled rate). Discount: k_eff = k / (1 + (k-1) rho), pooled_eff = sum x k_eff / k. rho = 0 equals the sum. Base case rho 0.3.

| method | cell | k | folds | sum /yr | rho=0 | rho=0.3 (base) | rho=0.6 | k_eff (0.3) |
|---|---|---|---|---|---|---|---|---|
| ICT | 1m-metals | 2 | 9 | 675.7 | 675.7 | 519.8 | 422.3 | 1.54 |
| ICT | 1m-indices | 5 | 4 | 1849.5 | 1849.5 | 840.7 | 544.0 | 2.27 |
| ICT | 5m-metals | 4 | 17 | 197.3 | 197.3 | 103.9 | 70.5 | 2.11 |
| ICT | 5m-indices | 13 | 4 | 726.8 | 726.8 | 158.0 | 88.6 | 2.83 |
| ICT | 15m-metals | 4 | 17 | 62.0 | 62.0 | 32.6 | 22.1 | 2.11 |
| ICT | 15m-indices | 13 | 4 | 235.3 | 235.3 | 51.2 | 28.7 | 2.83 |
| ICT | 30m-metals | 4 | 17 | 22.7 | 22.7 | 11.9 | 8.1 | 2.11 |
| ICT | 30m-indices | 13 | 4 | 112.3 | 112.3 | 24.4 | 13.7 | 2.83 |
| WYCKOFF | 1m-metals | 2 | 9 | 448.7 | 448.7 | 345.2 | 280.4 | 1.54 |
| WYCKOFF | 1m-indices | 5 | 4 | 1213.0 | 1213.0 | 551.4 | 356.8 | 2.27 |
| WYCKOFF | 5m-metals | 4 | 17 | 200.0 | 200.0 | 105.3 | 71.4 | 2.11 |
| WYCKOFF | 5m-indices | 13 | 4 | 589.8 | 589.8 | 128.2 | 71.9 | 2.83 |
| WYCKOFF | 15m-metals | 4 | 17 | 81.7 | 81.7 | 43.0 | 29.2 | 2.11 |
| WYCKOFF | 15m-indices | 13 | 4 | 215.2 | 215.2 | 46.8 | 26.2 | 2.83 |
| WYCKOFF | 30m-metals | 4 | 17 | 19.7 | 19.7 | 10.4 | 7.0 | 2.11 |
| WYCKOFF | 30m-indices | 13 | 4 | 55.0 | 55.0 | 12.0 | 6.7 | 2.83 |

### T3-base. Power of the harness lower-bound rule, N = candidate set (PRIMARY: discounted rate (rho 0.3), regime rho 0.3)


ICT, N = 232, confidence 0.999569; P(rule returns > 0), 200 replications per cell and e

| cell | E[n] at e=0.20 | e=0.10 | e=0.15 | e=0.20 | e=0.25 | e=0.30 | e=0.35 | e=0.40 | e_min (grid) | e_min (interp) | P(all folds >= 30) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1m-metals | 4689 | 0.38 | 0.93 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.150 | 0.135 | 1.00 |
| 1m-indices | 3346 | 0.14 | 0.47 | 0.80 | 0.94 | 1.00 | 1.00 | 1.00 | 0.225 | 0.201 | 1.00 |
| 5m-metals | 1770 | 0.17 | 0.55 | 0.86 | 1.00 | 1.00 | 1.00 | 1.00 | 0.200 | 0.189 | 1.00 |
| 5m-indices | 636 | 0.00 | 0.00 | 0.11 | 0.22 | 0.40 | 0.55 | 0.72 | 0.500 | 0.458 | 1.00 |
| 15m-metals | 557 | 0.01 | 0.07 | 0.23 | 0.38 | 0.67 | 0.86 | 0.91 | 0.350 | 0.328 | 0.00 |
| 15m-indices | 206 | 0.00 | 0.00 | 0.01 | 0.01 | 0.01 | 0.11 | 0.12 | 0.800 | 0.794 | 0.98 |
| 30m-metals | 204 | 0.00 | 0.01 | 0.01 | 0.04 | 0.14 | 0.15 | 0.36 | 0.600 | 0.572 | 0.00 |
| 30m-indices | 99 | 0.00 | 0.00 | 0.00 | 0.01 | 0.01 | 0.02 | 0.00 | n/a | n/a | 0.00 |

WYCKOFF, N = 128, confidence 0.999219; P(rule returns > 0), 200 replications per cell and e

| cell | E[n] at e=0.20 | e=0.10 | e=0.15 | e=0.20 | e=0.25 | e=0.30 | e=0.35 | e=0.40 | e_min (grid) | e_min (interp) | P(all folds >= 30) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1m-metals | 3069 | 0.28 | 0.81 | 0.99 | 1.00 | 1.00 | 1.00 | 1.00 | 0.150 | 0.149 | 1.00 |
| 1m-indices | 2220 | 0.07 | 0.37 | 0.72 | 0.91 | 0.96 | 0.99 | 1.00 | 0.250 | 0.227 | 1.00 |
| 5m-metals | 1793 | 0.15 | 0.61 | 0.88 | 0.99 | 1.00 | 1.00 | 1.00 | 0.175 | 0.169 | 1.00 |
| 5m-indices | 513 | 0.01 | 0.03 | 0.10 | 0.14 | 0.34 | 0.52 | 0.68 | 0.500 | 0.459 | 1.00 |
| 15m-metals | 727 | 0.05 | 0.15 | 0.41 | 0.71 | 0.91 | 0.97 | 1.00 | 0.300 | 0.276 | 0.30 |
| 15m-indices | 187 | 0.00 | 0.00 | 0.01 | 0.01 | 0.06 | 0.09 | 0.14 | 0.800 | 0.749 | 0.96 |
| 30m-metals | 176 | 0.00 | 0.01 | 0.04 | 0.04 | 0.09 | 0.19 | 0.28 | 0.600 | 0.574 | 0.00 |
| 30m-indices | 48 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.01 | n/a | n/a | 0.00 |

### T3-sum03. Power of the harness lower-bound rule, N = candidate set (undiscounted sum rate, regime rho 0.3)


ICT, N = 232, confidence 0.999569; P(rule returns > 0), 200 replications per cell and e

| cell | E[n] at e=0.20 | e=0.10 | e=0.15 | e=0.20 | e=0.25 | e=0.30 | e=0.35 | e=0.40 | e_min (grid) | e_min (interp) | P(all folds >= 30) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1m-metals | 6051 | 0.65 | 0.99 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.125 | 0.116 | 1.00 |
| 1m-indices | 7399 | 0.29 | 0.85 | 0.98 | 0.99 | 1.00 | 1.00 | 1.00 | 0.150 | 0.145 | 1.00 |
| 5m-metals | 3350 | 0.40 | 0.90 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.150 | 0.134 | 1.00 |
| 5m-indices | 2909 | 0.06 | 0.38 | 0.80 | 0.91 | 0.99 | 1.00 | 1.00 | 0.200 | 0.200 | 1.00 |
| 15m-metals | 1048 | 0.04 | 0.18 | 0.51 | 0.87 | 0.99 | 1.00 | 1.00 | 0.250 | 0.238 | 0.96 |
| 15m-indices | 939 | 0.01 | 0.06 | 0.16 | 0.35 | 0.57 | 0.79 | 0.86 | 0.375 | 0.354 | 1.00 |
| 30m-metals | 386 | 0.00 | 0.01 | 0.10 | 0.21 | 0.41 | 0.58 | 0.79 | 0.500 | 0.405 | 0.00 |
| 30m-indices | 451 | 0.00 | 0.01 | 0.01 | 0.07 | 0.16 | 0.31 | 0.47 | 0.600 | 0.554 | 1.00 |

WYCKOFF, N = 128, confidence 0.999219; P(rule returns > 0), 200 replications per cell and e

| cell | E[n] at e=0.20 | e=0.10 | e=0.15 | e=0.20 | e=0.25 | e=0.30 | e=0.35 | e=0.40 | e_min (grid) | e_min (interp) | P(all folds >= 30) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1m-metals | 4070 | 0.38 | 0.93 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.150 | 0.133 | 1.00 |
| 1m-indices | 4848 | 0.29 | 0.73 | 0.96 | 1.00 | 1.00 | 1.00 | 1.00 | 0.175 | 0.161 | 1.00 |
| 5m-metals | 3382 | 0.43 | 0.93 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.150 | 0.134 | 1.00 |
| 5m-indices | 2352 | 0.10 | 0.43 | 0.74 | 0.92 | 0.99 | 0.99 | 1.00 | 0.225 | 0.215 | 1.00 |
| 15m-metals | 1385 | 0.14 | 0.45 | 0.77 | 0.96 | 0.99 | 1.00 | 1.00 | 0.225 | 0.206 | 1.00 |
| 15m-indices | 860 | 0.01 | 0.05 | 0.15 | 0.39 | 0.62 | 0.81 | 0.93 | 0.350 | 0.338 | 1.00 |
| 30m-metals | 338 | 0.01 | 0.01 | 0.09 | 0.15 | 0.32 | 0.58 | 0.78 | 0.500 | 0.412 | 0.00 |
| 30m-indices | 220 | 0.00 | 0.01 | 0.01 | 0.04 | 0.05 | 0.07 | 0.20 | 0.800 | 0.718 | 0.97 |

### T3-rho0. Power of the harness lower-bound rule, N = candidate set (sum rate, regime rho 0)


ICT, N = 232, confidence 0.999569; P(rule returns > 0), 200 replications per cell and e

| cell | E[n] at e=0.20 | e=0.10 | e=0.15 | e=0.20 | e=0.25 | e=0.30 | e=0.35 | e=0.40 | e_min (grid) | e_min (interp) | P(all folds >= 30) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1m-metals | 6069 | 0.64 | 0.99 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.125 | 0.117 | 1.00 |
| 1m-indices | 7418 | 0.49 | 0.91 | 0.99 | 1.00 | 1.00 | 1.00 | 1.00 | 0.150 | 0.132 | 1.00 |
| 5m-metals | 3348 | 0.42 | 0.92 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.150 | 0.134 | 1.00 |
| 5m-indices | 2912 | 0.12 | 0.48 | 0.77 | 0.95 | 0.99 | 1.00 | 1.00 | 0.225 | 0.208 | 1.00 |
| 15m-metals | 1053 | 0.04 | 0.17 | 0.54 | 0.86 | 0.96 | 0.99 | 1.00 | 0.250 | 0.241 | 1.00 |
| 15m-indices | 941 | 0.00 | 0.07 | 0.18 | 0.41 | 0.60 | 0.83 | 0.93 | 0.350 | 0.344 | 1.00 |
| 30m-metals | 385 | 0.01 | 0.01 | 0.09 | 0.23 | 0.37 | 0.66 | 0.81 | 0.400 | 0.398 | 0.00 |
| 30m-indices | 447 | 0.00 | 0.01 | 0.03 | 0.10 | 0.20 | 0.41 | 0.45 | 0.600 | 0.534 | 1.00 |

WYCKOFF, N = 128, confidence 0.999219; P(rule returns > 0), 200 replications per cell and e

| cell | E[n] at e=0.20 | e=0.10 | e=0.15 | e=0.20 | e=0.25 | e=0.30 | e=0.35 | e=0.40 | e_min (grid) | e_min (interp) | P(all folds >= 30) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1m-metals | 4043 | 0.47 | 0.94 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.150 | 0.134 | 1.00 |
| 1m-indices | 4855 | 0.41 | 0.80 | 0.97 | 1.00 | 1.00 | 1.00 | 1.00 | 0.175 | 0.151 | 1.00 |
| 5m-metals | 3394 | 0.48 | 0.91 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.150 | 0.134 | 1.00 |
| 5m-indices | 2363 | 0.07 | 0.42 | 0.78 | 0.94 | 0.99 | 1.00 | 1.00 | 0.225 | 0.206 | 1.00 |
| 15m-metals | 1397 | 0.13 | 0.45 | 0.82 | 0.95 | 1.00 | 1.00 | 1.00 | 0.200 | 0.198 | 1.00 |
| 15m-indices | 865 | 0.03 | 0.06 | 0.22 | 0.42 | 0.67 | 0.86 | 0.95 | 0.350 | 0.331 | 1.00 |
| 30m-metals | 334 | 0.01 | 0.04 | 0.06 | 0.20 | 0.42 | 0.56 | 0.73 | 0.500 | 0.433 | 0.00 |
| 30m-indices | 220 | 0.00 | 0.01 | 0.01 | 0.04 | 0.07 | 0.07 | 0.20 | 0.800 | 0.694 | 1.00 |

### T3-rho06. Power of the harness lower-bound rule, N = candidate set (rate discounted at rho 0.6, regime rho 0.6)


ICT, N = 232, confidence 0.999569; P(rule returns > 0), 200 replications per cell and e

| cell | E[n] at e=0.20 | e=0.10 | e=0.15 | e=0.20 | e=0.25 | e=0.30 | e=0.35 | e=0.40 | e_min (grid) | e_min (interp) | P(all folds >= 30) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1m-metals | 3795 | 0.25 | 0.81 | 0.98 | 1.00 | 1.00 | 1.00 | 1.00 | 0.150 | 0.149 | 1.00 |
| 1m-indices | 2189 | 0.06 | 0.17 | 0.56 | 0.84 | 0.93 | 0.98 | 0.99 | 0.250 | 0.245 | 1.00 |
| 5m-metals | 1200 | 0.06 | 0.26 | 0.61 | 0.89 | 0.98 | 0.99 | 1.00 | 0.250 | 0.230 | 0.99 |
| 5m-indices | 357 | 0.01 | 0.01 | 0.01 | 0.04 | 0.10 | 0.15 | 0.39 | 0.600 | 0.577 | 1.00 |
| 15m-metals | 373 | 0.00 | 0.01 | 0.07 | 0.18 | 0.41 | 0.61 | 0.76 | 0.500 | 0.423 | 0.00 |
| 15m-indices | 113 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.03 | 0.04 | n/a | n/a | 0.03 |
| 30m-metals | 139 | 0.00 | 0.00 | 0.00 | 0.01 | 0.07 | 0.11 | 0.14 | 0.800 | 0.741 | 0.00 |
| 30m-indices | 55 | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | 0.01 | 0.00 | n/a | n/a | 0.00 |

WYCKOFF, N = 128, confidence 0.999219; P(rule returns > 0), 200 replications per cell and e

| cell | E[n] at e=0.20 | e=0.10 | e=0.15 | e=0.20 | e=0.25 | e=0.30 | e=0.35 | e=0.40 | e_min (grid) | e_min (interp) | P(all folds >= 30) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1m-metals | 2505 | 0.19 | 0.70 | 0.95 | 1.00 | 1.00 | 1.00 | 1.00 | 0.175 | 0.166 | 1.00 |
| 1m-indices | 1423 | 0.04 | 0.10 | 0.36 | 0.66 | 0.91 | 0.95 | 0.97 | 0.300 | 0.280 | 1.00 |
| 5m-metals | 1213 | 0.06 | 0.34 | 0.69 | 0.95 | 0.99 | 1.00 | 1.00 | 0.225 | 0.215 | 0.99 |
| 5m-indices | 288 | 0.00 | 0.01 | 0.01 | 0.06 | 0.11 | 0.21 | 0.30 | 0.800 | 0.624 | 1.00 |
| 15m-metals | 493 | 0.00 | 0.06 | 0.21 | 0.39 | 0.67 | 0.84 | 0.92 | 0.350 | 0.343 | 0.00 |
| 15m-indices | 104 | 0.00 | 0.00 | 0.01 | 0.01 | 0.02 | 0.03 | 0.07 | n/a | n/a | 0.01 |
| 30m-metals | 119 | 0.01 | 0.00 | 0.01 | 0.06 | 0.04 | 0.11 | 0.17 | 0.800 | 0.733 | 0.00 |
| 30m-indices | 27 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | n/a | n/a | 0.00 |

### T3-avail. Power of the harness lower-bound rule, N = candidate set (availability-aware (late symbols absent before first bar), discounted rate, rho 0.3)


ICT, N = 232, confidence 0.999569; P(rule returns > 0), 200 replications per cell and e

| cell | E[n] at e=0.20 | e=0.10 | e=0.15 | e=0.20 | e=0.25 | e=0.30 | e=0.35 | e=0.40 | e_min (grid) | e_min (interp) | P(all folds >= 30) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 5m-metals | 1369 | 0.08 | 0.38 | 0.75 | 0.94 | 1.00 | 1.00 | 1.00 | 0.225 | 0.210 | 0.28 |
| 5m-indices | 624 | 0.01 | 0.01 | 0.03 | 0.20 | 0.31 | 0.51 | 0.71 | 0.500 | 0.461 | 1.00 |
| 15m-metals | 429 | 0.01 | 0.03 | 0.05 | 0.24 | 0.48 | 0.68 | 0.85 | 0.400 | 0.383 | 0.00 |
| 15m-indices | 203 | 0.00 | 0.00 | 0.00 | 0.01 | 0.03 | 0.06 | 0.12 | 1.000 | 0.811 | 0.94 |
| 30m-metals | 154 | 0.00 | 0.01 | 0.01 | 0.03 | 0.09 | 0.09 | 0.19 | 0.800 | 0.692 | 0.00 |
| 30m-indices | 97 | 0.00 | 0.01 | 0.00 | 0.00 | 0.01 | 0.01 | 0.01 | n/a | n/a | 0.00 |

WYCKOFF, N = 128, confidence 0.999219; P(rule returns > 0), 200 replications per cell and e

| cell | E[n] at e=0.20 | e=0.10 | e=0.15 | e=0.20 | e=0.25 | e=0.30 | e=0.35 | e=0.40 | e_min (grid) | e_min (interp) | P(all folds >= 30) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 5m-metals | 1383 | 0.10 | 0.41 | 0.76 | 0.95 | 1.00 | 1.00 | 1.00 | 0.225 | 0.208 | 0.41 |
| 5m-indices | 507 | 0.01 | 0.03 | 0.08 | 0.18 | 0.34 | 0.47 | 0.64 | 0.500 | 0.467 | 1.00 |
| 15m-metals | 559 | 0.04 | 0.08 | 0.17 | 0.48 | 0.73 | 0.86 | 0.97 | 0.325 | 0.319 | 0.00 |
| 15m-indices | 184 | 0.00 | 0.00 | 0.01 | 0.02 | 0.04 | 0.09 | 0.14 | 0.800 | 0.770 | 0.87 |
| 30m-metals | 136 | 0.01 | 0.00 | 0.01 | 0.04 | 0.04 | 0.11 | 0.20 | 0.800 | 0.694 | 0.00 |
| 30m-indices | 47 | 0.00 | 0.00 | 0.01 | 0.00 | 0.01 | 0.00 | 0.01 | n/a | n/a | 0.00 |

### T4. e_star: net edge at which prop_pass_probability (120-day horizon) first reaches 0.70 (bisection, 9 steps), per fund and binding

| variant | method | cell | trades/yr (pooled used) | e* FTMO | e* The5ers | binding e* |
|---|---|---|---|---|---|---|
| base | ICT | 1m-metals | 520 | 0.172 | 0.143 | 0.172 |
| base | ICT | 1m-indices | 841 | 0.176 | 0.156 | 0.176 |
| base | ICT | 5m-metals | 104 | 0.125 | 0.096 | 0.125 |
| base | ICT | 5m-indices | 158 | 0.133 | 0.107 | 0.133 |
| base | ICT | 15m-metals | 33 | 0.146 | 0.123 | 0.146 |
| base | ICT | 15m-indices | 51 | 0.129 | 0.105 | 0.129 |
| base | ICT | 30m-metals | 12 | 0.127 | 0.100 | 0.127 |
| base | ICT | 30m-indices | 24 | 0.119 | 0.092 | 0.119 |
| base | WYCKOFF | 1m-metals | 345 | 0.166 | 0.146 | 0.166 |
| base | WYCKOFF | 1m-indices | 551 | 0.195 | 0.176 | 0.195 |
| base | WYCKOFF | 5m-metals | 105 | 0.139 | 0.119 | 0.139 |
| base | WYCKOFF | 5m-indices | 128 | 0.113 | 0.094 | 0.113 |
| base | WYCKOFF | 15m-metals | 43 | 0.135 | 0.117 | 0.135 |
| base | WYCKOFF | 15m-indices | 47 | 0.105 | 0.084 | 0.105 |
| base | WYCKOFF | 30m-metals | 10 | 0.127 | 0.100 | 0.127 |
| base | WYCKOFF | 30m-indices | 12 | 0.129 | 0.111 | 0.129 |
| sum03 | ICT | 1m-metals | 676 | 0.207 | 0.180 | 0.207 |
| sum03 | ICT | 1m-indices | 1850 | 0.268 | 0.256 | 0.268 |
| sum03 | ICT | 5m-metals | 197 | 0.125 | 0.104 | 0.125 |
| sum03 | ICT | 5m-indices | 727 | 0.195 | 0.168 | 0.195 |
| sum03 | ICT | 15m-metals | 62 | 0.129 | 0.104 | 0.129 |
| sum03 | ICT | 15m-indices | 235 | 0.125 | 0.102 | 0.125 |
| sum03 | ICT | 30m-metals | 23 | 0.121 | 0.100 | 0.121 |
| sum03 | ICT | 30m-indices | 112 | 0.107 | 0.090 | 0.107 |
| sum03 | WYCKOFF | 1m-metals | 449 | 0.156 | 0.137 | 0.156 |
| sum03 | WYCKOFF | 1m-indices | 1213 | 0.246 | 0.225 | 0.246 |
| sum03 | WYCKOFF | 5m-metals | 200 | 0.111 | 0.090 | 0.111 |
| sum03 | WYCKOFF | 5m-indices | 590 | 0.160 | 0.139 | 0.160 |
| sum03 | WYCKOFF | 15m-metals | 82 | 0.104 | 0.084 | 0.104 |
| sum03 | WYCKOFF | 15m-indices | 215 | 0.127 | 0.111 | 0.127 |
| sum03 | WYCKOFF | 30m-metals | 20 | 0.115 | 0.092 | 0.115 |
| sum03 | WYCKOFF | 30m-indices | 55 | 0.113 | 0.098 | 0.113 |
| rho0 | ICT | 1m-metals | 676 | 0.217 | 0.191 | 0.217 |
| rho0 | ICT | 1m-indices | 1850 | 0.256 | 0.244 | 0.256 |
| rho0 | ICT | 5m-metals | 197 | 0.117 | 0.090 | 0.117 |
| rho0 | ICT | 5m-indices | 727 | 0.152 | 0.137 | 0.152 |
| rho0 | ICT | 15m-metals | 62 | 0.105 | 0.082 | 0.105 |
| rho0 | ICT | 15m-indices | 235 | 0.121 | 0.096 | 0.121 |
| rho0 | ICT | 30m-metals | 23 | 0.129 | 0.100 | 0.129 |
| rho0 | ICT | 30m-indices | 112 | 0.137 | 0.119 | 0.137 |
| rho0 | WYCKOFF | 1m-metals | 449 | 0.139 | 0.111 | 0.139 |
| rho0 | WYCKOFF | 1m-indices | 1213 | 0.236 | 0.217 | 0.236 |
| rho0 | WYCKOFF | 5m-metals | 200 | 0.125 | 0.105 | 0.125 |
| rho0 | WYCKOFF | 5m-indices | 590 | 0.180 | 0.160 | 0.180 |
| rho0 | WYCKOFF | 15m-metals | 82 | 0.111 | 0.094 | 0.111 |
| rho0 | WYCKOFF | 15m-indices | 215 | 0.115 | 0.098 | 0.115 |
| rho0 | WYCKOFF | 30m-metals | 20 | 0.135 | 0.107 | 0.135 |
| rho0 | WYCKOFF | 30m-indices | 55 | 0.123 | 0.098 | 0.123 |
| rho06 | ICT | 1m-metals | 422 | 0.162 | 0.143 | 0.162 |
| rho06 | ICT | 1m-indices | 544 | 0.203 | 0.182 | 0.203 |
| rho06 | ICT | 5m-metals | 70 | 0.107 | 0.086 | 0.107 |
| rho06 | ICT | 5m-indices | 89 | 0.111 | 0.096 | 0.111 |
| rho06 | ICT | 15m-metals | 22 | 0.141 | 0.115 | 0.141 |
| rho06 | ICT | 15m-indices | 29 | 0.113 | 0.088 | 0.113 |
| rho06 | ICT | 30m-metals | 8 | 0.117 | 0.094 | 0.117 |
| rho06 | ICT | 30m-indices | 14 | 0.113 | 0.086 | 0.113 |
| rho06 | WYCKOFF | 1m-metals | 280 | 0.145 | 0.125 | 0.145 |
| rho06 | WYCKOFF | 1m-indices | 357 | 0.148 | 0.125 | 0.148 |
| rho06 | WYCKOFF | 5m-metals | 71 | 0.135 | 0.111 | 0.135 |
| rho06 | WYCKOFF | 5m-indices | 72 | 0.117 | 0.090 | 0.117 |
| rho06 | WYCKOFF | 15m-metals | 29 | 0.115 | 0.088 | 0.115 |
| rho06 | WYCKOFF | 15m-indices | 26 | 0.115 | 0.088 | 0.115 |
| rho06 | WYCKOFF | 30m-metals | 7 | 0.121 | 0.098 | 0.121 |
| rho06 | WYCKOFF | 30m-indices | 7 | 0.135 | 0.109 | 0.135 |

### T5. Rule verdict at k = 2, PRIMARY variant, N = candidate set (ICT 232, Wyckoff 128)

| cell | method | e_min | e_min (interp) | e_star | ratio | ratio (interp) | <= 2 ? |
|---|---|---|---|---|---|---|---|
| 1m-metals | ICT | 0.150 | 0.135 | 0.172 | 0.87 | 0.78 | yes |
| 1m-metals | WYCKOFF | 0.150 | 0.149 | 0.166 | 0.90 | 0.90 | yes |
| 1m-indices | ICT | 0.225 | 0.201 | 0.176 | 1.28 | 1.14 | yes |
| 1m-indices | WYCKOFF | 0.250 | 0.227 | 0.195 | 1.28 | 1.16 | yes |
| 5m-metals | ICT | 0.200 | 0.189 | 0.125 | 1.60 | 1.51 | yes |
| 5m-metals | WYCKOFF | 0.175 | 0.169 | 0.139 | 1.26 | 1.22 | yes |
| 5m-indices | ICT | 0.500 | 0.458 | 0.133 | 3.76 | 3.45 | no |
| 5m-indices | WYCKOFF | 0.500 | 0.459 | 0.113 | 4.41 | 4.05 | no |
| 15m-metals | ICT | 0.350 | 0.328 | 0.146 | 2.39 | 2.24 | no |
| 15m-metals | WYCKOFF | 0.300 | 0.276 | 0.135 | 2.23 | 2.05 | no |
| 15m-indices | ICT | 0.800 | 0.794 | 0.129 | 6.21 | 6.16 | no |
| 15m-indices | WYCKOFF | 0.800 | 0.749 | 0.105 | 7.59 | 7.10 | no |
| 30m-metals | ICT | 0.600 | 0.572 | 0.127 | 4.73 | 4.51 | no |
| 30m-metals | WYCKOFF | 0.600 | 0.574 | 0.127 | 4.73 | 4.53 | no |
| 30m-indices | ICT | n/a | n/a | 0.119 | n/a | n/a | no |
| 30m-indices | WYCKOFF | n/a | n/a | 0.129 | n/a | n/a | no |

### T6. Included cells by k (cell included iff min over methods of ratio <= k), N = candidate set

| variant | k=1.5 | k=2 | k=2.5 | k=3 |
|---|---|---|---|---|
| base | 1m-metals, 1m-indices, 5m-metals | 1m-metals, 1m-indices, 5m-metals | 1m-metals, 1m-indices, 5m-metals, 15m-metals | 1m-metals, 1m-indices, 5m-metals, 15m-metals |
| sum03 | 1m-metals, 1m-indices, 5m-metals, 5m-indices | 1m-metals, 1m-indices, 5m-metals, 5m-indices, 15m-metals | 1m-metals, 1m-indices, 5m-metals, 5m-indices, 15m-metals | 1m-metals, 1m-indices, 5m-metals, 5m-indices, 15m-metals, 15m-indices |
| rho0 | 1m-metals, 1m-indices, 5m-metals, 5m-indices | 1m-metals, 1m-indices, 5m-metals, 5m-indices, 15m-metals | 1m-metals, 1m-indices, 5m-metals, 5m-indices, 15m-metals | 1m-metals, 1m-indices, 5m-metals, 5m-indices, 15m-metals, 15m-indices |
| rho06 | 1m-metals, 1m-indices | 1m-metals, 1m-indices, 5m-metals | 1m-metals, 1m-indices, 5m-metals | 1m-metals, 1m-indices, 5m-metals |
| avail | none | 5m-metals | 5m-metals, 15m-metals | 5m-metals, 15m-metals |

Best ratio per cell (min over methods), by variant, N = candidate set (n/a = e_min not reached on the grid up to 1.0)

| cell | base | sum03 | rho0 | rho06 | avail |
|---|---|---|---|---|---|
| 1m-metals | 0.87 | 0.60 | 0.58 | 0.93 | n/a |
| 1m-indices | 1.28 | 0.56 | 0.59 | 1.23 | n/a |
| 5m-metals | 1.26 | 1.20 | 1.20 | 1.67 | 1.62 |
| 5m-indices | 3.76 | 1.02 | 1.25 | 5.39 | 3.76 |
| 15m-metals | 2.23 | 1.94 | 1.80 | 3.04 | 2.41 |
| 15m-indices | 6.21 | 2.76 | 2.89 | n/a | 7.59 |
| 30m-metals | 4.73 | 4.13 | 3.10 | 6.61 | 6.30 |
| 30m-indices | n/a | 5.59 | 4.39 | n/a | n/a |

### T7. Same verdict at the FINAL included-set N (ICT 87, Wyckoff 48), PRIMARY variant

| cell | method | e_min | e_star | ratio | <= 2 ? |
|---|---|---|---|---|---|
| 1m-metals | ICT | 0.125 | 0.172 | 0.73 | yes |
| 1m-metals | WYCKOFF | 0.150 | 0.166 | 0.90 | yes |
| 1m-indices | ICT | 0.200 | 0.176 | 1.14 | yes |
| 1m-indices | WYCKOFF | 0.200 | 0.195 | 1.02 | yes |
| 5m-metals | ICT | 0.175 | 0.125 | 1.40 | yes |
| 5m-metals | WYCKOFF | 0.175 | 0.139 | 1.26 | yes |
| 5m-indices | ICT | 0.400 | 0.133 | 3.01 | no |
| 5m-indices | WYCKOFF | 0.400 | 0.113 | 3.53 | no |
| 15m-metals | ICT | 0.325 | 0.146 | 2.22 | no |
| 15m-metals | WYCKOFF | 0.275 | 0.135 | 2.04 | no |
| 15m-indices | ICT | 0.800 | 0.129 | 6.21 | no |
| 15m-indices | WYCKOFF | 0.800 | 0.105 | 7.59 | no |
| 30m-metals | ICT | 0.600 | 0.127 | 4.73 | no |
| 30m-metals | WYCKOFF | 0.600 | 0.127 | 4.73 | no |
| 30m-indices | ICT | 1.000 | 0.119 | 8.39 | no |
| 30m-indices | WYCKOFF | n/a | 0.129 | n/a | no |

Included by k at the final N: k=1.5: 1m-metals, 1m-indices, 5m-metals; k=2.0: 1m-metals, 1m-indices, 5m-metals; k=2.5: 1m-metals, 1m-indices, 5m-metals, 15m-metals; k=3.0: 1m-metals, 1m-indices, 5m-metals, 15m-metals

## 5. Verdict, recommendation and what it depends on
Primary variant (base), k = 2, N for the 8-cell candidate set (ICT 29 x 8 = 232, confidence 1 - 0.10/232 = 0.999569; Wyckoff 16 x 8 = 128, 0.999219), table T5:
- INCLUDED: **1m-metals, 1m-indices, 5m-metals** (best ratios 0.87, 1.28, 1.26).
- EXCLUDED: 5m-indices (best ratio 3.76), 15m-metals (2.23 Wyckoff, 2.39 ICT), 15m-indices (6.21), 30m-metals (4.73), 30m-indices (e_min not reached by e = 1.0).
- **Recommended included-cell list: 1m-metals, 1m-indices, 5m-metals (3 cells).** Final N = ICT 29 x 3 = 87 (confidence 1 - 0.10/87 = 0.998851),
  Wyckoff 16 x 3 = 48 (0.997917). Iterated once (T7, same streams, lower confidence): the included set is unchanged (ratios 0.73 / 0.90, 1.14 / 1.02, 1.40 / 1.26;
  15m-metals Wyckoff 2.04 and ICT 2.22, still just above 2; 5m-indices 3.01 at best).
- Sensitivity in k (T6, primary variant): k = 1.5 and 2 give the same 3 cells; k = 2.5 and 3 add 15m-metals. 15m-metals is the one cell whose inclusion
  hinges on k (ratio 2.2 to 2.4; 2.05 for Wyckoff with the interpolated e_min, so it sits at the boundary at k = 2).
- Dependence on the pooling variant (T6): with the undiscounted sum (sum03 / rho0) 5m-indices (best ratio 1.02-1.25) and 15m-metals (1.80-1.94) also pass at k = 2,
  and 15m-indices at k = 3; with the discount at 0.6 (3 cells) or the availability-aware metals model (only 5m-metals at k = 2) the set shrinks. The 1m cells have no
  avail run (no late symbols in the model), so "none" at k = 1.5 for avail is not a 1m failure. The recommendation on 5m-indices and 15m-metals is therefore not robust to
  how correlated the index symbols' trades really are: the most decision-relevant unverified quantity. The 30m cells fail under every variant (best ratio 3.1, 30m-metals
  at rho 0; the 30m-indices' e_min is beyond the grid in most variants): the larger symbol set did not give them enough trades (about 10-23 per year for the 4 metals
  depending on method and discount, 12-112 for the 13 indices), so the 2026-10-01 removal of both 30m cells is not reversed by this rule.
- 1m-indices has ratio 1.28 in the primary variant against 0.56-0.59 undiscounted: it is included in every variant, but its margin is set by the discount.

## 6. Insufficient-fold guard (P(every test fold >= MIN_FOLD_TRADES = 30))
Column "P(all folds >= 30)" of T3. Primary variant (ICT / Wyckoff): 1m-metals 1.00 / 1.00, 1m-indices 1.00 / 1.00, 5m-metals 1.00 / 1.00, 5m-indices 1.00 / 1.00,
15m-metals 0.00 / 0.30, 15m-indices 0.98 / 0.96, 30m-metals 0.00 / 0.00, 30m-indices 0.00 / 0.00. The 5m-metals 1.00 assumes all four symbols trade in all 17 folds; in the
availability-aware variant it is 0.28 for ICT (early folds hold only XAUUSD and XAGUSD), so an included cell can still be flagged `insufficient` in its early folds.

## 7. Caveats
1. **Pooling correlation is an unverified model parameter.** Neither the discount formula nor rho = 0.3 was measured (no cross-symbol trade-overlap statistic was
   computed; that needs entry timestamps, not counts). The primary variant double-counts it; the sum variants ignore trade-level overlap.
2. **Rates come from 2021-03-01..2024-03-01 only** (3 one-year slices) and are extrapolated to all F folds (up to 17 years for the metals). Year-to-year spread is
   visible in T1 (for example XPDUSD ICT 5m 50 / 72 / 34).
3. **Late-start / sparse symbols.** Slices with < 90 % of the best coverage are excluded from the rate (`*` in T1): the S1 slice of most index symbols (DE40, FRA40, US500,
   USTEC, UK100, EU50, JP225, HK50, SPN35), so their rate rests on two slices. N25 is the extreme: its S2 and S3 are sparse (5m in-slice bars 6 382 / 9 669 against 31 952
   in S1), so its rate is its S1 count alone (ICT 5m 26) while its S2/S3 counts (5 / 6) are lower bounds from a mostly empty series. SPN35 and N25 have no history before
   2020-11 and enter only part of fold 0. XPTUSD / XPDUSD have no data in test folds 0-6.
4. **Binary-outcome model:** +2.5R / -1R with cost 0.07R, no time-stops, partials or breakevens; e is a net edge under that model, not a statement about any cell.
5. One baseline value set (b10 convention); V overlays that add trades would raise the rates. Admitted trades are counted per symbol; overlapping signals across
   symbols are not de-duplicated.
6. e_min is a grid value with Monte-Carlo SE up to 0.035 in power, so ratios within about 15 % of 2 (15m-metals Wyckoff 2.23, 2.04 interpolated) are not resolved. e_star
   comes from a 9-step bisection on a 20000-trade stream and is model-dependent; it is not monotone in the trade rate (daily-loss limits bind differently at different
   trades per day).
7. k = 2 is post-hoc (section 1). The inclusion list is an input to the owner's decision, not a declaration.

## 8. Reproduce
```
export BT_HISTORY_ROOT=data/history/ftmo
S_NEW="XPTUSD XPDUSD UK100 EU50 JP225 HK50 AUS200 US2000 SPN35 N25"; S_OLD="XAUUSD XAGUSD US500 US30 USTEC DE40 FRA40"
python3 scripts/research/trade_rates.py run --out /tmp/b16-results.jsonl --workers 4 --timeout 1800 --symbols $S_NEW --tfs 5m 15m 30m
python3 scripts/research/trade_rates.py run --out /tmp/b16-results.jsonl --workers 4 --timeout 1800 --symbols $S_OLD --tfs 30m
python3 scripts/research/trade_rates.py coverage --out /tmp/b16-coverage.json --symbols $S_NEW $S_OLD --tfs 5m 15m 30m
python3 scripts/research/cell_selection.py rates --results /tmp/b16-results.jsonl --coverage /tmp/b16-coverage.json --out /tmp/b16-rates.json
python3 scripts/research/cell_selection.py power --rates /tmp/b16-rates.json --out /tmp/b16-power.json --reps 200            # about 15 min, 4 processes
python3 scripts/research/cell_selection.py power --rates /tmp/b16-rates.json --out /tmp/b16-power-final.json --reps 200 \
    --only "cs|base|" --final-n-ict 87 --final-n-wyckoff 48                                                                  # about 5 min
python3 scripts/research/cell_selection.py report --rates /tmp/b16-rates.json --power /tmp/b16-power.json \
    --power-final /tmp/b16-power-final.json --out /tmp/b16-tables.md
```
The counts run took about 50 min wall (5m jobs up to 122 s each). The committed JSON artefacts are `docs/audits/2026-10-01-cell-selection-{rates,power,power-final}.json`
and `-counts.jsonl`; the coverage JSON (per-symbol in-slice bar counts) was a scratch input and is summarised in the rates JSON (`slice_bars`, `complete`).
