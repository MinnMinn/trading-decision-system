# Fund-search shard time model, calibrated with real measurements (2026-10-01)

Branch `b14-shard-calibration`, from `windows-migration` f5eb338, merged with `windows-migration` 3cc3ba2 (the declared plan is now three cells). Scope: replace the one-run, uncalibrated shard time model of
`docs/audits/2026-09-30-actions-sharding.md` (section 3, 581 s first set + 213 s per further set) with a model fitted to real scans of the
harness's own engine on real FTMO history, and re-lay the Actions shard matrix with it. **Counts, seconds and bytes only: no R, expectancy
or any performance figure was read, printed or stored** (a grep of the raw rows for the performance-metric terms returns nothing).
Nothing was declared, evaluated, pushed or merged; no full-span scan was run; at most 4 processes ran at a time. The statistics, the plan,
the grids and the cells are untouched: `plan --dry-run` prints `plan_hash 4a476bee674afcbb` (the 3-cell plan of 3cc3ba2), identical before and after this branch's changes (it was f7d67a77ef1e9e20 for the earlier 6-cell plan at f5eb338).

**Pinned file changed:** `scripts/fund-search.py` is in `FINGERPRINT_FILES` (the code fingerprint of every declaration and scan-cache
stamp). No declaration exists yet in this branch, so nothing needs re-declaring, but `declare` must be run from the FINAL code. **The model
constants live in that file**, so recalibrating (for example with a measured runner factor, section 7) after `declare` would change the
fingerprint: do any recalibration BEFORE `declare`. Other files: `scripts/tests/test_fund_search.py` (tests), new research tooling
`scripts/research/shard_calibration.py`, `scripts/research/shard_calibration_fit.py`, the raw rows in
`docs/audits/2026-10-01-shard-calibration-data/`.

## 1. Answer

1. **The old model was 2.3-4.4x too pessimistic per runner core and wrong in structure.** One ICT detection group over the whole 1m XAUUSD span
   is ~44 min of one core (0.646 ms per bar), not 581 s x 10 workers = 97 min; and an extra value set in the same group is ~6 min (13 % of a group at 1m), not 213 s x 10 = 35 min.
   Wave 1 of one 1m metals symbol, unsliced at factor 1.0: ICT 1,020 min (old) -> 233 min, Wyckoff 1,117 min -> 479 min.
   The 581 s "first set" is what this model predicts for a full 15m XAUUSD ICT scan (453,893 bars x 1.35 ms = 613 s), which confirms the suspicion in the
   old section 3 that it was a 15m number carried over.
2. **What matters is the number of DETECTION GROUPS, not the number of value sets.** `scan_many` shares one analysis pass between value sets that agree on
   the analysis-affecting keys. With the real grids, wave 1 has **2 detection groups for the 27 ICT sets** (only B-POOL varies: 26 + 1) and **9 groups
   for the 14 Wyckoff sets** (6 + 8 singletons: W4a x2, W6 = 600, W-TW x5). ICT extra sets are cheap (3-13 % of a group), Wyckoff extra sets are free (a new set
   almost always opens a new group, which costs a full scan; the W6 = 600 group costs 1.3-1.9x a default-window group).
3. **Layout now (factor 2.0 slow-runner assumption): 124 shards, no shard over 300 modelled minutes (longest 291 min), 400.0 runner-hours** (the old model: 212 shards,
   40,485 minutes = 675 runner-hours, longest 274 min). At factor 1.0 the same layout costs 206.8 runner-hours (longest 148 min), at 1.5 it costs 303.1 (longest 220 min). This is the declared THREE-cell plan (1m-metals, 1m-indices, 5m-metals incl. XPTUSD/XPDUSD; plan_hash 4a476bee674afcbb, windows-migration 3cc3ba2 merged into this branch).
4. **1m metals is 89 % of the work** (184 of 207 runner-hours at factor 1.0, 88 of the 124 shards) because the memory clamp runs it with ONE worker per shard.
   The other four (cell, method) rows are 23 runner-hours together.
5. **Honest uncertainty:** the runner's per-core speed relative to this Mac is UNKNOWN and scales every figure linearly; the full 12-year 1m scans were not run (the cost is extrapolated from
   one-year slices; linearity was verified up to 4 years); wave 2 depends on the selection and was measured on 8 real folds only. See section 7.
6. **Finding outside the brief (section 8): `trades_for` raises on a real ICT 1m value set.** `B-EX = fill` produces trades whose entry price equals their stop on the
   1m cells (XAUUSD: 1 trade in the S3 year; US500: 80), and `real_costs.cost_r` refuses a zero stop distance, so a `run` of the 1m ICT cells would abort at that value set. The scans themselves are fine.

## 2. Method

* **Machine:** Apple M3 Pro, 12 cores, 38 GB RAM, Python 3.14.5, shared with other users (load average 5-40 during the runs, recorded per row). One process per measurement, in-process
  `scan_many` (`workers=1`), at most 4 measurement processes at a time. This is the REFERENCE machine of the model.
* **Engine path:** the harness's own `BtEngine(...).scan_symbol(symbol, value_sets)` (= one `scan_many` call = what an Actions shard persists), the harness's own
  `wave1_values` / `wave2_values` / `build_overlay`, the real grids (`docs/architecture/v-grid-*.json`), real FTMO history (`BT_HISTORY_ROOT=data/history/ftmo`), PIT cutoff 2024-03-01.
  Nothing in the engine was modified.
* **Slicing:** the one-year cut of `scripts/research/trade_rates.py` (decision series cut to `[start - 14 d - scan window, end + 5 d]`; higher-timeframe series untouched).
  S3 = 2023-03-01..2024-03-01 (the last development year). Multi-worker runs use the harness's own `dev_start` cut instead, because spawned workers reload the series and would
  bypass a wrapped `bt.load`. `scripts/research/shard_calibration.py` (jobs `scan`, `scan_dev`, `groups`, `load`, `wave2`, `trades_for`, `cache_io`, `entry_eq_stop`, `bars`).
* **Cost structure fitted** (`scripts/research/shard_calibration_fit.py`, pure Python, non-negative weighted least squares):

  `seconds(one scan_many call) = a + bars x ( G300 x g300 + G600 x g600 + S x (value sets - groups) )`

  `g300`/`g600` = detection groups on the default / the W6 = 600 Wyckoff window (ICT: all `g300`), `S` = one more value set inside an existing group, `a` = per-call fixed seconds
  (Wyckoff: the fitted intercept, independent of the bar count, origin not identified, see 3.9; ICT: 0 - its one-group points cannot separate `a` from `G`).
* **Value sets used:** real wave-1 sets of the real grids, in the harness's discovery order (`w1:<i>`). ICT same-group designs n = 1, 2, 4, 8, 16, 26 (all share B-POOL = off), two-group designs
  (+ the B-POOL = on set), and the full 27-set wave 1; Wyckoff same-group n = 1, 2, 4, 6, 8 (the last two literal multi-factor assignments of the grid), one set per group for all 9 groups,
  g = 2, 3, 5 and the full 14-set / 9-group wave 1.
* **Held-out:** the biggest designs (the full-wave-1 shapes) were left out of the fit and predicted (section 3.4).

## 3. Measured tables

All seconds are wall seconds of the call on the reference machine, including the one-time load of the process. "Raw trades" = trades the scan returned (count only).

### 3.1 Cost of ONE detection group (baseline value set), one year, S3

| method | symbol | tf | bars in slice | seconds | ms/bar | raw trades | machine load avg (start/end) |
|---|---|---|---|---|---|---|---|
| ict | US500 | 15m | 25225 | 28.92 | 1.146 | 35 | 8.3/8.4 |
| ict | XAUUSD | 15m | 25225 | 27.39 | 1.086 | 28 | 7.8/8.8 |
| ict | US500 | 1m | 352871 | 265.01 | 0.751 | 1579 | 6.2/8.4 |
| ict | XAUUSD | 1m | 366100 | 240.4 | 0.657 | 867 | 6.2/7.8 |
| ict | US500 | 5m | 73692 | 84.45 | 1.146 | 128 | 7.8/7.2 |
| ict | XAUUSD | 5m | 73730 | 84.18 | 1.142 | 103 | 7.8/8.3 |
| wyckoff | US500 | 15m | 24949 | 4.01 | 0.161 | 34 | 8.4/8.3 |
| wyckoff | XAUUSD | 15m | 24949 | 5.59 | 0.224 | 31 | 8.0/7.8 |
| wyckoff | US500 | 1m | 352811 | 108.46 | 0.307 | 505 | 6.2/7.2 |
| wyckoff | XAUUSD | 1m | 366040 | 496.44 | 1.356 | 605 | 6.2/13.5 |
| wyckoff | US500 | 5m | 73416 | 13.2 | 0.180 | 95 | 8.3/7.8 |
| wyckoff | XAUUSD | 5m | 73454 | 20.84 | 0.284 | 120 | 7.8/7.2 |

Noise: repeating the same measurement changes it by about +/-10 %, and on a loaded machine by up to ~20 % (Wyckoff XAUUSD 1m baseline: 496 s in the first run at load 6, 601 s in two later runs at load 10-16;
ICT 5m baseline: 84.2, 84.4, 87.7 and 77.8 s). The fit pools all points rather than trusting one.
Wyckoff's cost depends strongly on the symbol: it is ~4x dearer per bar on XAUUSD 1m than on US500 1m because the W7 target reads an HTF prefix that is 1.3 M bars long for the metals (history from 2004) and ~0.2 M for the indices (from 2017).

### 3.2 Position in the history (metals; one-year slices spread over the span, baseline set)

| method | symbol | tf | slice | bars | seconds | ms/bar | raw trades |
|---|---|---|---|---|---|---|---|
| ict | XAUUSD | 15m | 2005-03..2006-03 | 22452 | 35.96 | 1.602 | 82 |
| ict | XAUUSD | 15m | 2008-03..2009-03 | 24742 | 39.2 | 1.584 | 66 |
| ict | XAUUSD | 15m | 2011-03..2012-03 | 24731 | 34.99 | 1.415 | 35 |
| ict | XAUUSD | 15m | 2014-03..2015-03 | 25384 | 33.5 | 1.320 | 23 |
| ict | XAUUSD | 15m | 2017-03..2018-03 | 25529 | 30.17 | 1.182 | 34 |
| ict | XAUUSD | 15m | 2020-03..2021-03 | 25624 | 30.59 | 1.194 | 21 |
| ict | XAUUSD | 15m | 2022-03..2023-03 | 25380 | 31.32 | 1.234 | 28 |
| ict | US30 | 1m | S3 | 365453 | 240.5 | 0.658 | 955 |
| ict | XAUUSD | 1m | 2013-03..2014-03 | 366530 | 244.3 | 0.667 | 903 |
| ict | XAUUSD | 1m | 2015-03..2016-03 | 368083 | 248.48 | 0.675 | 1020 |
| ict | XAUUSD | 1m | 2017-03..2018-03 | 368187 | 241.37 | 0.656 | 727 |
| ict | XAUUSD | 1m | 2019-03..2020-03 | 369109 | 249.98 | 0.677 | 876 |
| ict | XAUUSD | 1m | 2021-03..2022-03 | 371707 | 249.25 | 0.671 | 923 |
| ict | XAUUSD | 5m | 2005-03..2006-03 | 55089 | 90.02 | 1.634 | 312 |
| ict | XAUUSD | 5m | 2008-03..2009-03 | 71942 | 98.28 | 1.366 | 240 |
| ict | XAUUSD | 5m | 2011-03..2012-03 | 72355 | 83.61 | 1.156 | 137 |
| ict | XAUUSD | 5m | 2014-03..2015-03 | 73896 | 84.17 | 1.139 | 83 |
| ict | XAUUSD | 5m | 2017-03..2018-03 | 74360 | 84.25 | 1.133 | 100 |
| ict | XAUUSD | 5m | 2020-03..2021-03 | 74751 | 84.12 | 1.125 | 85 |
| ict | XAUUSD | 5m | 2022-03..2023-03 | 74191 | 90.69 | 1.222 | 115 |
| wyckoff | XAUUSD | 15m | 2005-03..2006-03 | 22176 | 4.51 | 0.203 | 25 |
| wyckoff | XAUUSD | 15m | 2008-03..2009-03 | 24466 | 5.06 | 0.207 | 24 |
| wyckoff | XAUUSD | 15m | 2011-03..2012-03 | 24455 | 5.15 | 0.211 | 38 |
| wyckoff | XAUUSD | 15m | 2014-03..2015-03 | 25108 | 4.54 | 0.181 | 25 |
| wyckoff | XAUUSD | 15m | 2017-03..2018-03 | 25253 | 5.13 | 0.203 | 36 |
| wyckoff | XAUUSD | 15m | 2020-03..2021-03 | 25348 | 4.89 | 0.193 | 39 |
| wyckoff | XAUUSD | 15m | 2022-03..2023-03 | 25104 | 6.44 | 0.257 | 45 |
| wyckoff | US30 | 1m | S3 | 365393 | 156.75 | 0.429 | 599 |
| wyckoff | XAUUSD | 1m | 2013-03..2014-03 | 366470 | 220.42 | 0.601 | 563 |
| wyckoff | XAUUSD | 1m | 2015-03..2016-03 | 368023 | 270.8 | 0.736 | 540 |
| wyckoff | XAUUSD | 1m | 2017-03..2018-03 | 368127 | 363.84 | 0.988 | 653 |
| wyckoff | XAUUSD | 1m | 2019-03..2020-03 | 369049 | 412.33 | 1.117 | 612 |
| wyckoff | XAUUSD | 1m | 2021-03..2022-03 | 371647 | 305.91 | 0.823 | 551 |
| wyckoff | XAUUSD | 5m | 2005-03..2006-03 | 54813 | 12.13 | 0.221 | 57 |
| wyckoff | XAUUSD | 5m | 2008-03..2009-03 | 71666 | 14.29 | 0.199 | 89 |
| wyckoff | XAUUSD | 5m | 2011-03..2012-03 | 72079 | 15.3 | 0.212 | 108 |
| wyckoff | XAUUSD | 5m | 2014-03..2015-03 | 73620 | 15.26 | 0.207 | 123 |
| wyckoff | XAUUSD | 5m | 2017-03..2018-03 | 74084 | 17.99 | 0.243 | 101 |
| wyckoff | XAUUSD | 5m | 2020-03..2021-03 | 74475 | 18.23 | 0.245 | 112 |
| wyckoff | XAUUSD | 5m | 2022-03..2023-03 | 73915 | 22.38 | 0.303 | 116 |

The model needs the cost of a FULL span, not of the last year. ICT is nearly position-independent at 1m (0.656-0.677 ms/bar) and costs more per bar early at 5m/15m (sparse early data);
Wyckoff on metals is dearer late (the W7 prefix grows): the position factor below is the mean over the slices divided by S3, applied to the group cost of the metals only (the indices are measured at S3 and used as measured, which is conservative).

| method | tf | slices | variable ms/bar by slice (old .. S3) | mean | S3 | factor |
|---|---|---|---|---|---|---|
| ict | 1m | 6 | 0.67, 0.68, 0.66, 0.68, 0.67, 0.66 | 0.667 | 0.657 | 1.016 |
| ict | 5m | 8 | 1.63, 1.37, 1.16, 1.14, 1.13, 1.13, 1.22, 1.16 | 1.242 | 1.159 | 1.072 |
| ict | 15m | 8 | 1.60, 1.58, 1.41, 1.32, 1.18, 1.19, 1.23, 1.18 | 1.339 | 1.181 | 1.134 |
| wyckoff | 1m | 6 | 0.41, 0.55, 0.80, 0.93, 0.63, 1.36 | 0.779 | 1.356 | 0.574 |
| wyckoff | 5m | 8 | 0.18, 0.17, 0.18, 0.18, 0.21, 0.22, 0.27, 0.27 | 0.212 | 0.273 | 0.775 |
| wyckoff | 15m | 8 | 0.17, 0.18, 0.18, 0.16, 0.18, 0.17, 0.23, 0.21 | 0.185 | 0.212 | 0.875 |

### 3.3 Marginal cost of value sets and of groups (XAUUSD, S3 slice, in-process)

Design names: `g<groups>-n<value sets>`; `single-<i>` = wave-1 set `w1:<i>` alone (0 baseline, 2 = W4a 3, 3 = W4a 4, 4 = W6 600, 9-13 = the five other W-TW values); `C-` batches ran at 5m/15m, `D-` at 1m; `repeat` = the baseline again (noise). Same-group ICT designs take the first n of the 26 sets that share B-POOL = off.

| method | tf | design | value sets | groups | bars | seconds | raw trades |
|---|---|---|---|---|---|---|---|
| ict | 15m | C-ict-g1-n1 | 1 | 1 | 25225 | 31.49 | 28 |
| ict | 15m | C-repeat-ict | 1 | 1 | 25225 | 30.46 | 28 |
| ict | 15m | C-ict-g1-n2 | 2 | 1 | 25225 | 32.89 | 164 |
| ict | 15m | C-ict-g1-n4 | 4 | 1 | 25225 | 30.8 | 333 |
| ict | 15m | C-ict-g1-n8 | 8 | 1 | 25225 | 33.12 | 445 |
| ict | 15m | C-ict-g1-n16 | 16 | 1 | 25225 | 41.98 | 669 |
| ict | 15m | C-ict-g1-n26 | 26 | 1 | 25225 | 53.75 | 946 |
| ict | 15m | C-ict-g2-n2 | 2 | 2 | 25225 | 63.65 | 56 |
| ict | 15m | C-ict-g2-n5 | 5 | 2 | 25225 | 65.65 | 361 |
| ict | 15m | C-ict-g2-n27 | 27 | 2 | 25225 | 88.2 | 974 |
| ict | 1m | D-ict-g1-n2 | 2 | 1 | 366100 | 257.52 | 3765 |
| ict | 1m | D-ict-g1-n8 | 8 | 1 | 366100 | 426.9 | 11573 |
| ict | 1m | D-ict-g1-n26 | 26 | 1 | 366100 | 999.88 | 26749 |
| ict | 1m | D-ict-g2-n27 | 27 | 2 | 366100 | 1283.67 | 27616 |
| ict | 5m | C-ict-g1-n1 | 1 | 1 | 73730 | 84.36 | 103 |
| ict | 5m | C-repeat-ict | 1 | 1 | 73730 | 87.71 | 103 |
| ict | 5m | C-ict-g1-n2 | 2 | 1 | 73730 | 83.71 | 486 |
| ict | 5m | C-ict-g1-n4 | 4 | 1 | 73730 | 99.08 | 1022 |
| ict | 5m | C-ict-g1-n8 | 8 | 1 | 73730 | 120.52 | 1434 |
| ict | 5m | C-ict-g1-n16 | 16 | 1 | 73730 | 149.89 | 2258 |
| ict | 5m | C-ict-g1-n26 | 26 | 1 | 73730 | 204.38 | 3249 |
| ict | 5m | C-ict-g2-n2 | 2 | 2 | 73730 | 178.62 | 206 |
| ict | 5m | C-ict-g2-n5 | 5 | 2 | 73730 | 196.41 | 1125 |
| ict | 5m | C-ict-g2-n27 | 27 | 2 | 73730 | 309.69 | 3352 |
| wyckoff | 15m | C-wy-single-0 | 1 | 1 | 24949 | 5.95 | 31 |
| wyckoff | 15m | C-wy-single-2 | 1 | 1 | 24949 | 5.91 | 31 |
| wyckoff | 15m | C-wy-single-3 | 1 | 1 | 24949 | 5.88 | 33 |
| wyckoff | 15m | C-wy-single-4 | 1 | 1 | 24949 | 10.91 | 36 |
| wyckoff | 15m | C-wy-single-9 | 1 | 1 | 24949 | 5.99 | 31 |
| wyckoff | 15m | C-wy-single-10 | 1 | 1 | 24949 | 6.08 | 31 |
| wyckoff | 15m | C-wy-single-11 | 1 | 1 | 24949 | 6.1 | 31 |
| wyckoff | 15m | C-wy-single-12 | 1 | 1 | 24949 | 6.07 | 31 |
| wyckoff | 15m | C-wy-single-13 | 1 | 1 | 24949 | 5.85 | 31 |
| wyckoff | 15m | C-repeat-wyckoff | 1 | 1 | 24949 | 5.82 | 31 |
| wyckoff | 15m | C-wy-g1-n2 | 2 | 1 | 24949 | 6.38 | 62 |
| wyckoff | 15m | C-wy-g1-n4 | 4 | 1 | 24949 | 6.36 | 124 |
| wyckoff | 15m | C-wy-g1-n6 | 6 | 1 | 24949 | 6.06 | 181 |
| wyckoff | 15m | C-wy-g1-n8 | 8 | 1 | 24949 | 7.35 | 238 |
| wyckoff | 15m | C-wy-g2-n2 | 2 | 2 | 24949 | 11.67 | 62 |
| wyckoff | 15m | C-wy-g3-n3 | 3 | 3 | 24949 | 17.95 | 95 |
| wyckoff | 15m | C-wy-g5-n5 | 5 | 5 | 24949 | 29.8 | 162 |
| wyckoff | 15m | C-wy-g9-n14 | 14 | 9 | 24949 | 52.81 | 436 |
| wyckoff | 1m | D-wy-single-4 | 1 | 1 | 366040 | 707.55 | 620 |
| wyckoff | 1m | D-wy-single-2 | 1 | 1 | 366040 | 601.5 | 627 |
| wyckoff | 1m | D-wy-single-9 | 1 | 1 | 366040 | 601.43 | 602 |
| wyckoff | 1m | D-wy-g1-n4 | 4 | 1 | 366040 | 523.35 | 2427 |
| wyckoff | 1m | D-wy-g5-n5 | 5 | 5 | 366040 | 2580.07 | 3105 |
| wyckoff | 1m | D-wy-g9-n14 | 14 | 9 | 366040 | 4586.59 | 8438 |
| wyckoff | 5m | C-wy-single-0 | 1 | 1 | 73454 | 21.03 | 120 |
| wyckoff | 5m | C-wy-single-2 | 1 | 1 | 73454 | 20.94 | 123 |
| wyckoff | 5m | C-wy-single-3 | 1 | 1 | 73454 | 21.44 | 125 |
| wyckoff | 5m | C-wy-single-4 | 1 | 1 | 73454 | 37.66 | 125 |
| wyckoff | 5m | C-wy-single-9 | 1 | 1 | 73454 | 21.95 | 118 |
| wyckoff | 5m | C-wy-single-10 | 1 | 1 | 73454 | 22.58 | 121 |
| wyckoff | 5m | C-wy-single-11 | 1 | 1 | 73454 | 22.58 | 116 |
| wyckoff | 5m | C-wy-single-12 | 1 | 1 | 73454 | 23.04 | 114 |
| wyckoff | 5m | C-wy-single-13 | 1 | 1 | 73454 | 23.36 | 117 |
| wyckoff | 5m | C-repeat-wyckoff | 1 | 1 | 73454 | 23.82 | 120 |
| wyckoff | 5m | C-wy-g1-n2 | 2 | 1 | 73454 | 22.83 | 240 |
| wyckoff | 5m | C-wy-g1-n4 | 4 | 1 | 73454 | 21.39 | 480 |
| wyckoff | 5m | C-wy-g1-n6 | 6 | 1 | 73454 | 21.96 | 694 |
| wyckoff | 5m | C-wy-g1-n8 | 8 | 1 | 73454 | 23.87 | 908 |
| wyckoff | 5m | C-wy-g2-n2 | 2 | 2 | 73454 | 47.22 | 243 |
| wyckoff | 5m | C-wy-g3-n3 | 3 | 3 | 73454 | 61.72 | 368 |
| wyckoff | 5m | C-wy-g5-n5 | 5 | 5 | 73454 | 110.24 | 611 |
| wyckoff | 5m | C-wy-g9-n14 | 14 | 9 | 73454 | 198.58 | 1653 |

Reading it: at 5m, ICT 1 / 8 / 26 sets in one group take 84 / 121 / 204 s (about +4.8 s per extra set = 5.7 % of a group), and a second group (the B-POOL = on set) adds ~90 s; at 1m the same designs take 240 / 427 / 1000 s (+30 s per extra set = 12.6 %).
Wyckoff 1 / 4 / 8 sets in the same group take 21 / 21 / 24 s at 5m, 9 groups take 199 s: every group is a full scan and every extra set in a group is nearly free.
The W6 = 600 group (`w1:4`) is 37.7 s vs 21 s at 5m (1.8x) and 707 s vs 601 s at 1m (1.2x).

### 3.4 The fit and its residuals (held-out)

| method | tf | points | a (s per call) | G300 (ms/bar) | G600 (ms/bar) | G600 / G300 | S (ms/bar) | S / G300 |
|---|---|---|---|---|---|---|---|---|
| ict | 1m | 5 | 0.0 | 0.636 | n/a | n/a | 0.0836 | 0.131 |
| ict | 5m | 11 | 0.0 | 1.162 | n/a | n/a | 0.0647 | 0.056 |
| ict | 15m | 11 | 0.0 | 1.190 | n/a | n/a | 0.0351 | 0.030 |
| wyckoff | 1m | 7 | 70.0 | 1.305 | 1.738 | 1.33 | 0.0000 | 0.000 |
| wyckoff | 5m | 19 | 2.1 | 0.273 | 0.474 | 1.74 | 0.0014 | 0.005 |
| wyckoff | 15m | 19 | 0.6 | 0.213 | 0.399 | 1.88 | 0.0051 | 0.024 |

| method | tf | design | groups | sets | measured s | predicted s (train on the small designs) | error | predicted s (leave-one-out) | error |
|---|---|---|---|---|---|---|---|---|---|
| ict | 15m | C-ict-g1-n26 | 1 | 26 | 53.75 | 47.3 | -12.0% | 50.7 | -5.7% |
| ict | 15m | C-ict-g2-n27 | 2 | 27 | 88.2 | 77.5 | -12.1% | 81.0 | -8.2% |
| ict | 1m | D-ict-g1-n26 | 1 | 26 | 999.88 | 909.4 | -9.1% | 995.4 | -0.4% |
| ict | 1m | D-ict-g2-n27 | 2 | 27 | 1283.67 | 1145.6 | -10.8% | 1208.3 | -5.9% |
| ict | 5m | C-ict-g1-n26 | 1 | 26 | 204.38 | 196.7 | -3.8% | 205.5 | +0.5% |
| ict | 5m | C-ict-g2-n27 | 2 | 27 | 309.69 | 282.6 | -8.8% | 286.4 | -7.5% |
| wyckoff | 15m | C-wy-g9-n14 | 9 | 14 | 52.81 | 54.2 | +2.7% | 54.2 | +2.7% |
| wyckoff | 1m | D-wy-g9-n14 | 9 | 14 | 4586.59 | 4452.6 | -2.9% | 4452.6 | -2.9% |
| wyckoff | 5m | C-wy-g9-n14 | 9 | 14 | 198.58 | 197.0 | -0.8% | 197.0 | -0.8% |

The model reproduces the held-out full-wave-1 shapes within **-12 % .. +3 %** when trained on the small designs only (ICT under-predicts by 4-12 %, the later sets of the grid are dearer than the first ones;
Wyckoff is within 3 %), and within **-8 % .. +3 %** leave-one-out. The shipped constants are the all-points fit times the position factor of 3.2, so they are not independent of these points; the held-out table is the honest test of the STRUCTURE (groups + extra sets), not of the full-span extrapolation.

Indices (US500, plus US30 at 1m): the group cost is taken as the measured baseline seconds per bar (the per-call term included, so slightly conservative); the ICT extra-set cost of the indices is scaled by the same ratio (ASSUMED: not measured on indices).

| method | tf | symbols | indices ms/bar (a included) | metals S3 ms/bar | ratio |
|---|---|---|---|---|---|
| ict | 1m | US500, US30 | 0.704 | 0.657 | 1.07 |
| ict | 5m | US500 | 1.146 | 1.159 | 0.99 |
| ict | 15m | US500 | 1.146 | 1.181 | 0.97 |
| wyckoff | 1m | US500, US30 | 0.369 | 1.548 | 0.24 |
| wyckoff | 5m | US500 | 0.180 | 0.302 | 0.60 |
| wyckoff | 15m | US500 | 0.161 | 0.237 | 0.68 |

### 3.5 Linearity in the span (single process, baseline set)

| method | tf | span | bars | seconds | ms/bar |
|---|---|---|---|---|---|
| ict | 15m | 2019-03..2024-03 | 119976 | 156.66 | 1.306 |
| ict | 15m | 2014-03..2024-03 | 238558 | 311.74 | 1.307 |
| ict | 1m | 2020-03..2024-03 | 1418096 | 923.21 | 0.651 |
| ict | 5m | 2021-03..2024-03 | 214475 | 231.69 | 1.080 |
| wyckoff | 15m | 2019-03..2024-03 | 119700 | 26.42 | 0.221 |
| wyckoff | 15m | 2014-03..2024-03 | 238282 | 48.32 | 0.203 |
| wyckoff | 1m | 2022-03..2024-03 | 716423 | 1011.01 | 1.411 |
| wyckoff | 5m | 2021-03..2024-03 | 214199 | 63.97 | 0.299 |

Per-bar cost is flat from one year to 2 (Wyckoff 1m), 3 (5m), 4 (ICT 1m) and 10 (15m) years (ICT 1m: 0.651 ms/bar over 4 years vs 0.657 over one; ICT 15m 1.306/1.307 over 5/10 years, the position effect of 3.2 included).
The full 4.1 M-bar 1m series is 11x the 1m slice used here and was NOT scanned (out of scope); the extrapolation beyond 4 years rests on linearity, see section 7.

### 3.6 Parallel efficiency (one-year span cut by `dev_start`)

| method | symbol | tf | sets/groups | workers | chunks | seconds | speed-up |
|---|---|---|---|---|---|---|---|
| ict | XAUUSD | 5m | 1/1 | 1 | 1 | 77.82 | 1.00 |
| ict | XAUUSD | 5m | 1/1 | 2 | 4 | 47.85 | 1.63 |
| ict | XAUUSD | 5m | 1/1 | 3 | 6 | 37.8 | 2.06 |
| ict | XAUUSD | 5m | 1/1 | 4 | 8 | 28.12 | 2.77 |
| wyckoff | XAUUSD | 5m | 4/4 | 1 | 1 | 85.84 | 1.00 |
| wyckoff | XAUUSD | 5m | 4/4 | 2 | 1 | 66.26 | 1.30 |
| wyckoff | XAUUSD | 5m | 4/4 | 4 | 2 | 44.46 | 1.93 |
| ict | US30 | 1m | 1/1 | 1 | 1 | 236.53 | 1.00 |
| ict | US30 | 1m | 1/1 | 4 | 8 | 84.1 | 2.81 |

Raw speed-ups are 1.63 / 2.06 / 2.77 (ICT 5m, 2 / 3 / 4 workers) and 2.81 (ICT US30 1m, 4 workers), 1.30 / 1.93 (Wyckoff, 2 / 4 workers). With the per-worker series reload (`task_overhead_s_per_bar`, 3.9) and the Wyckoff per-call term counted explicitly, the remaining efficiency
(speed-up / workers) computes to 1.00 / 0.93 / 1.02 (ICT 5m) and 0.85 (ICT US30 1m at 4), 0.83 / 0.77 (Wyckoff at 2 / 4). The shipped values are the conservative 0.95 / 0.90 / 0.88 (ICT) and 0.83 / 0.80 / 0.77 (Wyckoff; 3 interpolated).
Wyckoff scales worse because the W6 = 600 group cannot be balanced against the others with 2 chunks per group. These runs are 1-year slices: tasks are short, so the explicit overhead is a larger share than on a full span.

### 3.7 Wave 2 (the selection's real requests, 2-3 real folds per cell shape)

Cells built with the harness's own engine on a later `dev_start` (3 folds: 2019-03-02..2024-03-01, 2 folds: 2020-03-01..2024-03-01), wave 1 scanned, `trades_for` run on every wave-1 set, then the harness's own `wave2_values`
(the real `nested_walk_forward` + `perturbation_trade_sets` against the held wave-1 trades). Only the NUMBER of requested sets and their detection groups were kept.

| method | cell shape | folds | symbols | wave-1 sets/groups | wave-2 sets (union over folds) | per fold alone | wave-2 groups | groups per fold alone | new groups vs wave 1 | wave-1 scan s |
|---|---|---|---|---|---|---|---|---|---|---|
| ict | 5m metals | 3 | 2 | 27/2 | 37 | [12, 14, 13] | 2 | - | 0 | 2776.3 |
| ict | 15m metals | 3 | 2 | 27/2 | 30 | [15, 15, 15] | 2 | - | 0 | 807.4 |
| ict | 15m indices | 2 | 5 | 27/2 | 23 | [13, 12] | 2 | - | 0 | 1266.5 |
| wyckoff | 5m metals | 3 | 2 | 14/9 | 27 | [9, 9, 9] | 12 | [5, 5, 4] | 11 | 1737.3 |
| wyckoff | 15m indices | 2 | 5 | 14/9 | 15 | [8, 9] | 7 | [4, 5] | 4 | 640.9 |
| wyckoff | 15m metals | 3 | 2 | 14/9 | 20 | [9, 8, 8] | 4 | [4, 4, 4] | 3 | 538.3 |

* **Sets per fold:** ICT 12.3, 10.0, 11.5 NEW sets per fold after de-duplication across folds (37/3, 30/3, 23/2); Wyckoff 9.0, 6.7, 7.5 (27/3, 20/3, 15/2). The shipped values are the means over the 8 folds, **ICT 11.25 and Wyckoff 7.75 per fold**
  (the earlier audit's zero-edge runs give ICT 8.7-10.8 per fold at 4-17 folds, Wyckoff 5.5-7.3; the reviewer's "up to 15 per fold" is the per-fold count BEFORE de-duplication, the "alone" column). The old assumption was 11 / 8.
* **Groups:** ICT wave 2 never has more than the same 2 groups. Wyckoff: 35 groups for 69 sets when each fold is taken alone (0.51 groups per set) and 24 of those 35 on the W6 = 600 window (0.69): once a fold selects W6 = 600, its chosen set and almost every perturbation of it are on the 600 window.
* **`wave2_values` itself costs nothing:** the nested walk-forward replay took < 0.05 s in every run; `trades_for` of 14-27 wave-1 sets took 0.2-1.6 s.

### 3.8 Memory

Fresh process: load of the full PIT-truncated series, then `BtEngine` construction, then the chunk arrays `scan_many` builds per worker (`_series` + id-of-time index):

| series | bars | RSS after load MiB | RSS after engine MiB | RSS after chunk arrays MiB | clamp estimate MiB | load s | engine build s | arrays s |
|---|---|---|---|---|---|---|---|---|
| XAUUSD 1m | 4096182 | 2619 | 3178 | 3434 | 3448 | 9.3 | 9.05 | 1.97 |
| XAUUSD 5m | 1316783 | 888 | 1018 | 1051 | 1195 | 2.86 | 2.87 | 0.72 |
| XAUUSD 15m | 453893 | 335 | 452 | 476 | 496 | 1.02 | 0.99 | 0.18 |
| US30 1m | 1729779 | 1379 | 1682 | 1756 | 1530 | 4.88 | 3.99 | 0.75 |
| XAGUSD 1m | 4097904 | 2652 | 3146 | 3436 | 3450 | 9.43 | 8.84 | 2.0 |
| US500 1m | 852695 | 1041 | 1084 | 1122 | 819 | 3.08 | 1.86 | 0.36 |

`scan_many.worker_memory_estimate` (128 MiB + 850 B x bars) matches the measured parent footprint for the big series (XAUUSD 1m: 3,434 vs 3,448 MiB; 15m: 476 vs 496) and **under-estimates the mid-size series by 15-37 %** (US30 1m 1,756 vs 1,530 MiB; US500 1m 1,122 vs 819).

Peak RSS of the one-year-slice scans of 3.1-3.3 (the process loaded the FULL series first, then cut it):

| method | symbol | tf | peak RSS MiB |
|---|---|---|---|
| ict | US500 | 15m | 120 |
| ict | XAUUSD | 15m | 346 |
| wyckoff | US500 | 15m | 142 |
| wyckoff | XAUUSD | 15m | 458 |
| ict | US30 | 1m | 1514 |
| ict | US500 | 1m | 1190 |
| ict | XAUUSD | 1m | 3318 |
| wyckoff | US30 | 1m | 1904 |
| wyckoff | US500 | 1m | 1425 |
| wyckoff | XAUUSD | 1m | 4242 |
| ict | US500 | 5m | 282 |
| ict | XAUUSD | 5m | 947 |
| wyckoff | US500 | 5m | 323 |
| wyckoff | XAUUSD | 5m | 1165 |

Peak RSS of a Wyckoff scan is ~0.9 GiB above ICT's on XAUUSD 1m (4,242 vs 3,318 MiB; these processes held the full 4.1 M-bar series and then scanned a slice): the W7 target's HTF indexes (the earlier audit's +0.5..1.4 GiB).

**Workers per 16 GB shard (decision):**
* **1m metals: 1 worker (in-process).** The clamp gives `floor(0.6 x 16 GiB / 3.46 GiB) - 1 = 1`. One process is ~3.4 GiB (ICT) / ~4.3 GiB (Wyckoff, with W7); a wave-2 shard holds BOTH metals series (2 x 3.1 GiB after `BtEngine`) plus the scan arrays, the W7 indexes and the held wave-1 trades
  (~1 KB per trade, ASSUMED, not measured): ~8-9 GiB, inside 16 GiB. Two workers would be ~10 GiB (ICT: parent 3.4 + 2 x 3.4) / ~13 GiB (Wyckoff: 4.3 + 2 x 4.3): technically possible but over the clamp's 60 % rule and too tight for Wyckoff; raising `MEMORY_FRACTION` is a pinned-file change in `scripts/scan_many.py` (not made).
* **1m indices (US30, 1.73 M bars), 5m and 15m cells: 4 workers** (the runner's vCPUs): 5 processes x ~1.8 GiB (US30 1m) = ~9 GiB, well inside 16 GiB. These cells are not memory-bound.
* **7 GiB private-repo runner:** the 1m-metals wave-2 shard (~8-9 GiB) would not fit; the model assumes the public-repo 16 GiB runner (not verified).

### 3.9 Per-shard fixed costs (reference machine)

| cost | measured | model constant |
|---|---|---|
| engine build = load + adx index + series sha256, per held bar | XAUUSD 1m 9.3 + 9.05 s for 4.10 M bars (4.5 us/bar); 5m 5.7 s / 1.32 M (4.3); 15m 2.0 s / 0.45 M (4.4); US30 1m 8.9 s / 1.73 M (5.1); US500 1m 4.9 s / 0.85 M (5.8) | `engine_build_s_per_bar` 5.0e-6, per symbol the engine holds (1 in wave 1, all of the cell's in wave 2) |
| per spawned scan worker: reload of the full series + arrays | 1m XAUUSD (9.3 + 1.97) s / 4.10 M = 2.7 us/bar; 5m 2.7; 15m 2.6; US30 3.3; US500 4.0 | `task_overhead_s_per_bar` 3.5e-6 (only when more than one worker runs) |
| Wyckoff per-call fixed term `a` | 70 s (1m), 2.1 s (5m), 0.6 s (15m), the fit's intercept. Its origin is not identified: the W7 audit's measured set-up is ~2.2 s per process (`docs/audits/2026-10-01-w7-speed.md` section 1), so at 1m most of the 70 s is something else. It is 1-2 % of a 1m shard, so it was kept as fitted | `call_fixed_s` (also repeated per spawned worker, conservative) |
| `trades_for` (simulate + admission rows + adx) | 4.0e-5 s per raw trade (0.04 s / 1,022 trades; 0.13 s / 3,067); a whole wave-2 probe run 0.2-1.6 s for 2,759-17,903 held trades (up to 9e-5 s per trade) | `trades_for_s_per_trade` 1.0e-4 |
| cache entry write / read + verify | ICT 1m: 426 B per trade, 0.03 s per entry written, 6.5e-6 s per trade read and hashed (8 entries, 11,573 trades: 0.075 s); Wyckoff 1m: 600 B per trade, 8e-6 s per trade | `cache_verify_s_per_trade` 1.0e-5, `cache_entry_s` 0.05 (assumed) |
| trades per bar (raw, mean per value set, XAUUSD) | ICT 2.8e-3 (1m), 1.7e-3 (5m), 1.4e-3 (15m); Wyckoff 1.7e-3, 1.6e-3, 1.3e-3 | `trades_per_bar` |

Post-processing is negligible next to the scans: the wave-2 fixed part of the biggest shard (1m metals) is ~1-2 minutes at factor 1.0. **Not measured:** checkout, Python setup and artifact up/download on a hosted runner (assumed `job_fixed_s` = 6 min per job).

## 4. The model (`scripts/fund-search.py`, `SHARD_MODEL`)

```
scan(method, tf, class, bars, groups, k sets) = call_fixed_s[method][tf]
        + bars x ( group_s_per_bar[method][tf][class] x sum(window factor of each group)
                   + (k - groups) x extra_set_s_per_bar[method][tf][class] )
        window factor = w600_group_factor[tf] for a Wyckoff W6 = 600 group, else 1
workers w = min(4, scan_many.clamp_workers(...))    # 1 for 1m metals
w > 1:  scan = (scan + (tasks - 1) x call_fixed + tasks x task_overhead_s_per_bar x bars) / (w x parallel_efficiency[method][w]),
        tasks = groups x ceil(2w / groups)
shard(factor) = factor x (scan + fixed) + job_fixed_s
fixed (wave 1) = engine_build_s_per_bar x bars(symbol)
fixed (wave 2) = engine build of every symbol of the cell + wave-1 cache verification + trades_for of every wave-1 set + select_s_per_fold x folds
```

`group_s_per_bar` and `extra_set_s_per_bar` are per (method, timeframe, asset class); the metals values are the fit times the position factor (3.2), the indices values are measured baselines (3.4). Wave-1 slices use the REAL group membership of the slice (data-free, from `scan_many`'s own key functions,
pinned equal to what `scan_many` really groups by `ShardGroupModel` on real scans); wave-2 slices use the measured groups-per-set (ICT capped at 2) and W6 = 600 share.
The slice count of every (cell, method, symbol, wave) is the smallest for which no slice is over `budget_s` (300 min) at `layout_factor` (2.0); a shard that is over the cap even with one value set (the irreducible unit) is flagged `over_cap`, not hidden. None is.

**Constants, measured vs assumed** (the same split is printed under `list-scan-shards --explain` and asserted by a test):

| constant | status | source |
|---|---|---|
| `group_s_per_bar`, `extra_set_s_per_bar`, `call_fixed_s`, `w600_group_factor` | MEASURED (extra sets of the indices: ASSUMED ratio) | 3.1-3.4 |
| `max_groups` (ICT 2, Wyckoff 36 = 2 windows x 3 W4a x 6 W-TW) | MEASURED from the grids and `scan_many`'s key | 2 |
| `parallel_efficiency` | MEASURED at 2 and 4 workers (3 interpolated), on M3 cores | 3.6 |
| `task_overhead_s_per_bar`, `engine_build_s_per_bar`, `trades_per_bar`, `cache_verify_s_per_trade`, `trades_for_s_per_trade` | MEASURED | 3.9 |
| `WAVE2_SETS_PER_FOLD`, `WAVE2_GROUPS_PER_SET`, `WAVE2_W600_GROUP_SHARE` | MEASURED on 8 real folds | 3.7 |
| runner = 4 vCPU / 16 GiB (`runner_vcpu`, `runner_ram_bytes`) | ASSUMED, not verified | GitHub's hosted `ubuntu-latest` for a public repo |
| runner speed factor 1.0 / 1.5 / 2.0 | ASSUMED parameter, never a measurement | section 7 |
| `job_fixed_s` 360, `plan_job_min` 5, `cache_entry_s`, `select_s_per_fold` | ASSUMED | not measured |
| `budget_s` 300 min, `job_timeout_min` 355 | policy (GitHub's cap is 360) | |
| `DEV_BARS` | unchanged: the audit's PIT-truncated bar counts. Re-measured here for all 21 (symbol, timeframe) rows: identical | `docs/audits/2026-10-01-shard-calibration-data/bars-check.json` |

## 5. Results

Layout fixed at the slow-runner factor 2.0 (`list-scan-shards` JSON: 124 shards, 38 wave 1 + 86 wave 2; every row has `est_min_f1`, `est_min_f1_5`, `est_min_f2`, `groups`, `over_cap`). The same layout evaluated at each factor:

| factor | shards | runner-hours | longest shard | critical path (plan + longest wave 1 + longest wave 2 + longest evaluate) |
|---|---|---|---|---|
| 1 | 124 | 206.8 | 148 min | 300 min (135 + 148 + 12) |
| 1.5 | 124 | 303.1 | 220 min | 441 min (200 + 220 + 16) |
| 2 | 124 | 400.0 | 291 min | 579 min (264 + 291 + 19) |

(The old uncalibrated model on the 6-cell plan: 212 shards, 675 runner-hours, longest 274 min; the plan has since been cut to 3 cells.) The critical path assumes unlimited concurrent runners; the workflow's `needs` are per job, so every cell waits for the slowest cell of the previous stage.

### Per (cell, method)

| cell | method | shards (w1 + w2) | runner-h @1.0 | @1.5 | @2.0 | longest shard min @1.0 / @1.5 / @2.0 | evaluate min @2.0 |
|---|---|---|---|---|---|---|---|
| 1m-metals | ict | 26 (6 + 20) | 59.0 | 87.1 | 115.1 | 148 / 220 / 291 | 19 |
| 1m-metals | wyckoff | 62 (14 + 48) | 125.2 | 183.9 | 243.4 | 128 / 188 / 249 | 12 |
| 1m-indices | ict | 10 (5 + 5) | 4.7 | 6.5 | 8.3 | 51 / 73 / 95 | 11 |
| 1m-indices | wyckoff | 10 (5 + 5) | 6.7 | 9.6 | 12.4 | 81 / 119 / 156 | 9 |
| 5m-metals | ict | 8 (4 + 4) | 6.2 | 8.8 | 11.5 | 105 / 154 / 204 | 13 |
| 5m-metals | wyckoff | 8 (4 + 4) | 5.1 | 7.2 | 9.3 | 91 / 133 / 175 | 11 |

### Wall time with a limited number of concurrent jobs

Greedy longest-first scheduling of each stage's shards on N identical runners; stages in series. **Hosted-runner concurrency limits were NOT verified** (they depend on the account's plan; I do not have a verified figure), so these are sensitivity rows, not a forecast.

| factor | concurrent jobs | wave 1 | wave 2 | evaluate | plan | total wall |
|---|---|---|---|---|---|---|
| 1 | 20 | 2.2 h | 8.8 h | 0.2 h | 5 min | 11.3 h |
| 1 | 60 | 2.2 h | 4.3 h | 0.2 h | 5 min | 6.8 h |
| 1 | unlimited | 2.2 h | 2.5 h | 0.2 h | 5 min | 5.0 h |
| 1.5 | 20 | 3.3 h | 12.9 h | 0.3 h | 5 min | 16.6 h |
| 1.5 | 60 | 3.3 h | 6.3 h | 0.3 h | 5 min | 9.9 h |
| 1.5 | unlimited | 3.3 h | 3.7 h | 0.3 h | 5 min | 7.3 h |
| 2 | 20 | 4.4 h | 17.1 h | 0.3 h | 5 min | 21.9 h |
| 2 | 60 | 4.4 h | 8.3 h | 0.3 h | 5 min | 13.1 h |
| 2 | unlimited | 4.4 h | 4.8 h | 0.3 h | 5 min | 9.7 h |

### Slices of the big cells

| cell | method | symbol | wave | slices | sets per slice (min-max) | groups per slice (max) | longest shard min @2.0 |
|---|---|---|---|---|---|---|---|
| 1m-metals | ict | XAUUSD | 1 | 3 | 9-9 | 2 | 264 |
| 1m-metals | ict | XAGUSD | 1 | 3 | 9-9 | 2 | 264 |
| 1m-metals | ict | XAUUSD | 2 | 10 | 10-11 | 2 | 291 |
| 1m-metals | ict | XAGUSD | 2 | 10 | 10-11 | 2 | 291 |
| 1m-metals | wyckoff | XAUUSD | 1 | 7 | 2-2 | 2 | 247 |
| 1m-metals | wyckoff | XAGUSD | 1 | 7 | 2-2 | 2 | 247 |
| 1m-metals | wyckoff | XAUUSD | 2 | 24 | 2-3 | 2 | 249 |
| 1m-metals | wyckoff | XAGUSD | 2 | 24 | 2-3 | 2 | 249 |
| 1m-indices | ict | US30 | 1 | 1 | 27-27 | 2 | 67 |
| 1m-indices | ict | US30 | 2 | 1 | 45-45 | 2 | 95 |
| 1m-indices | wyckoff | US30 | 1 | 1 | 14-14 | 9 | 78 |
| 1m-indices | wyckoff | US30 | 2 | 1 | 31-31 | 16 | 156 |
| 5m-metals | ict | XAUUSD | 1 | 1 | 27-27 | 2 | 59 |
| 5m-metals | ict | XAGUSD | 1 | 1 | 27-27 | 2 | 49 |
| 5m-metals | ict | XPTUSD | 1 | 1 | 27-27 | 2 | 26 |
| 5m-metals | ict | XPDUSD | 1 | 1 | 27-27 | 2 | 25 |
| 5m-metals | ict | XAUUSD | 2 | 1 | 192-192 | 2 | 204 |
| 5m-metals | ict | XAGUSD | 2 | 1 | 192-192 | 2 | 165 |
| 5m-metals | ict | XPTUSD | 2 | 1 | 192-192 | 2 | 81 |
| 5m-metals | ict | XPDUSD | 2 | 1 | 192-192 | 2 | 79 |
| 5m-metals | wyckoff | XAUUSD | 1 | 1 | 14-14 | 9 | 36 |
| 5m-metals | wyckoff | XAGUSD | 1 | 1 | 14-14 | 9 | 30 |
| 5m-metals | wyckoff | XPTUSD | 1 | 1 | 14-14 | 9 | 17 |
| 5m-metals | wyckoff | XPDUSD | 1 | 1 | 14-14 | 9 | 17 |
| 5m-metals | wyckoff | XAUUSD | 2 | 1 | 132-132 | 36 | 175 |
| 5m-metals | wyckoff | XAGUSD | 2 | 1 | 132-132 | 36 | 142 |
| 5m-metals | wyckoff | XPTUSD | 2 | 1 | 132-132 | 36 | 71 |
| 5m-metals | wyckoff | XPDUSD | 2 | 1 | 132-132 | 36 | 69 |

### `list-scan-shards --explain` (layout factor 2.0)

```
cell        method  symbol  wave slices  sets groups  longest shard  over 300 min?
1m-metals   ict     XAUUSD  1         3    27      4        264 min   no
1m-metals   ict     XAGUSD  1         3    27      4        264 min   no
1m-metals   ict     XAUUSD  2        10   102     20        291 min   no
1m-metals   ict     XAGUSD  2        10   102     20        291 min   no
1m-metals   wyckoff XAUUSD  1         7    14     12        247 min   no
1m-metals   wyckoff XAGUSD  1         7    14     12        247 min   no
1m-metals   wyckoff XAUUSD  2        24    70     48        249 min   no
1m-metals   wyckoff XAGUSD  2        24    70     48        249 min   no
1m-indices  ict     US500   1         1    27      2         36 min   no
1m-indices  ict     US30    1         1    27      2         67 min   no
1m-indices  ict     USTEC   1         1    27      2         36 min   no
1m-indices  ict     DE40    1         1    27      2         32 min   no
1m-indices  ict     FRA40   1         1    27      2         34 min   no
1m-indices  ict     US500   2         1    45      2         51 min   no
1m-indices  ict     US30    2         1    45      2         95 min   no
1m-indices  ict     USTEC   2         1    45      2         52 min   no
1m-indices  ict     DE40    2         1    45      2         46 min   no
1m-indices  ict     FRA40   2         1    45      2         49 min   no
1m-indices  wyckoff US500   1         1    14      9         45 min   no
1m-indices  wyckoff US30    1         1    14      9         78 min   no
1m-indices  wyckoff USTEC   1         1    14      9         46 min   no
1m-indices  wyckoff DE40    1         1    14      9         41 min   no
1m-indices  wyckoff FRA40   1         1    14      9         43 min   no
1m-indices  wyckoff US500   2         1    31     16         87 min   no
1m-indices  wyckoff US30    2         1    31     16        156 min   no
1m-indices  wyckoff USTEC   2         1    31     16         88 min   no
1m-indices  wyckoff DE40    2         1    31     16         79 min   no
1m-indices  wyckoff FRA40   2         1    31     16         83 min   no
5m-metals   ict     XAUUSD  1         1    27      2         59 min   no
5m-metals   ict     XAGUSD  1         1    27      2         49 min   no
5m-metals   ict     XPTUSD  1         1    27      2         26 min   no
5m-metals   ict     XPDUSD  1         1    27      2         25 min   no
5m-metals   ict     XAUUSD  2         1   192      2        204 min   no
5m-metals   ict     XAGUSD  2         1   192      2        165 min   no
5m-metals   ict     XPTUSD  2         1   192      2         81 min   no
5m-metals   ict     XPDUSD  2         1   192      2         79 min   no
5m-metals   wyckoff XAUUSD  1         1    14      9         36 min   no
5m-metals   wyckoff XAGUSD  1         1    14      9         30 min   no
5m-metals   wyckoff XPTUSD  1         1    14      9         17 min   no
5m-metals   wyckoff XPDUSD  1         1    14      9         17 min   no
5m-metals   wyckoff XAUUSD  2         1   132     36        175 min   no
5m-metals   wyckoff XAGUSD  2         1   132     36        142 min   no
5m-metals   wyckoff XPTUSD  2         1   132     36         71 min   no
5m-metals   wyckoff XPDUSD  2         1   132     36         69 min   no
total shards: 124; modelled runner minutes at factor 2: 23999
model constants: MEASURED (group_s_per_bar, extra_set_s_per_bar, call_fixed_s, w600_group_factor, max_groups, parallel_efficiency, task_overhead_s_per_bar, engine_build_s_per_bar, trades_per_bar, cache_verify_s_per_trade, trades_for_s_per_trade, WAVE2_SETS_PER_FOLD, WAVE2_GROUPS_PER_SET, WAVE2_W600_GROUP_SHARE; docs/audits/2026-10-01-shard-calibration.md) | ASSUMED (runner_vcpu, runner_ram_bytes, job_fixed_s, plan_job_min, cache_entry_s, select_s_per_fold, layout_factor, report_factors, budget_s, job_timeout_min; the runner-speed factor is a parameter, never a measurement)
```

## 6. Recommendation

1. **Run everything on Actions, 1m metals first in priority, but record the runner benchmark BEFORE `declare`.** The model is linear in the runner factor and the layout depends on it; the factor is the one thing that was not measured.
   `.github/workflows/fund-search-benchmark.yml` (workflow_dispatch only, `contents: read`, no secrets, output outside the checkout, ~10 min) runs `scripts/research/runner_benchmark.py`: five fixed one-year XAUUSD jobs (ICT 5m and Wyckoff 5m on one worker,
   ICT 5m and a 4-group Wyckoff 5m on 4 workers, the 1m full-series load), prints each job's seconds, the reference-machine seconds and the implied factor, and uploads `runner-benchmark.json` (with `layout_factor` = the worse of the two single-process factors, rounded up to 0.25).
   **How it is recorded:** the owner downloads the artifact, commits it as `docs/audits/2026-10-01-runner-benchmark.json`, sets `SHARD_MODEL["layout_factor"]` (pinned `scripts/fund-search.py`) to its `layout_factor`, re-runs `list-scan-shards --explain`, then `declare`.
   `declare` records the file's sha256 in the declaration (`runner_benchmark`) and prints a NOTE to stderr when the file is missing or its `layout_factor` differs from the model's; it never refuses (the owner decides: the layout sizes jobs, it cannot change a result). The workflow was not triggered.
   Its 4-worker rows also show the parallel efficiency the runner really gives (the model assumes 0.77-0.88); if the 4-worker speed-up is well below ~2.8x (ICT) the hyper-thread caveat of section 7 applies and the layout factor should be raised.
   **Wave-2 tripwire:** wave 2 is only known at run time. `scan --wave 2` compares the real list with the layout's estimate and, when it is more than 10 % longer, prints `WARNING: ... Re-run EVERY wave-2 slice of <cell>/<method>/<symbol> with --slice I/N` to stderr (visible in the job log). The override is a re-run of that (cell, method, symbol)'s slices with the printed N
   (matrix entries are plain `--slice I/N` arguments; entries are keyed per value set, so a different N yields the same cache). **Persistence:** a shard writes its entries after its single `scan_many` call returns (the slice shares each detection group's analysis, so scanning set by set would multiply the cost); a shard killed at the timeout keeps nothing of its slice, which is what the slice sizing bounds. The `scan` docstring now says so (it previously promised per-set persistence).
2. **Cells.** Actions is where 1m metals (ICT 26 shards, Wyckoff 62; ~89 % of the work) pays off: on this Mac (10 workers clamped to ~5 by the 36 GB memory rule) the same cells take about 43 h of wall time (model: ICT 13 h + Wyckoff 31 h at factor 1.0, per-job overhead removed), on Actions about 5-10 h critical path if enough jobs run at once.
   The other four rows (1m indices, 5m metals; 23 runner-hours at factor 1.0, 36 shards) take about 2 h on this Mac (10 workers) and could be run locally while the 1m metals shards run on Actions; running them through the same workflow keeps one provenance path (one commit, one artifact lineage), which I recommend unless Actions concurrency turns out to be low.
   Any shard that fails or times out can be re-run locally with `fund-search.py scan ... --slice I/N`: slicing never changes a value.
3. **Expected total wall time** (all 6 rows of the 3-cell plan): **5.0 h / 7.3 h / 9.7 h** at factors 1.0 / 1.5 / 2.0 with unlimited concurrency; 6.8 / 9.9 / 13.1 h with 60 concurrent jobs; 11.3 / 16.6 / 21.9 h with 20. Total runner-hours 207 / 303 / 400. Add queueing and retries.
4. **Do not rely on the minute figures beyond a factor of ~2 either way**: see section 7. The layout, not the minutes, is the deliverable: it makes no shard modelled over 300 min at factor 2.0, i.e. a runner up to 2x slower than this Mac still finishes every shard inside GitHub's 360 min cap with ~55 min to spare.
5. **Optional, not done (pinned files / out of scope):** (a) group-aware slicing of the ICT lists (put the B-POOL = off and = on sets in different slices) would save one group pass per slice, ~25 % of the ICT 1m-metals runner-hours; (b) raising `scan_many.MEMORY_FRACTION` would give 1m metals 2 workers (~1.6x on ~89 % of the work) at a memory risk for Wyckoff;
   (c) a bar-range split below one value set is not needed in this model (the irreducible unit, a Wyckoff W6 = 600 group on 1m metals, is 145 min including the job overhead at factor 2.0; a single ICT set is 95 min).

## 7. Assumptions and honest uncertainty

* **Runner speed (dominant, unknown).** Every shard figure scales linearly with the factor; the layout was made for 2.0. A hosted `ubuntu-latest` core can be slower than an M3 core by more than 2x (I have no measurement). Its 4 vCPUs are probably hyper-threads, so 4 parallel workers may reach less than the 0.77-0.88 efficiency measured on 4 real cores (affects the cells that run 4 workers, ~11 % of the runner-hours).
* **Extrapolation to the full span.** Slices of 1 year, 11x shorter than the 1m metals series; linear to 4 years (ICT 1m), 3 years (5m), 10 years (15m), 2 years (Wyckoff 1m). A superlinear component beyond that would make 1m metals dearer; none was observed.
* **The single largest model-error lever: Wyckoff 1m metals** (~60 % of the runner-hours, 125 of 207 at factor 1.0). Its group cost is the fit (1.305 ms/bar at the last year) times a position factor of **0.574** taken from six one-year slices measured on a loaded shared machine (per-slice 0.41-1.36 ms/bar); a +/-15 % error on that factor moves the total by about +/-9 % (+/-15 % of 60 %), more than any other single constant except the runner factor. A measurement of two more mid-history slices on a quiet machine would tighten it.
* **Conservative double-count for the indices:** the indices' Wyckoff group rate is the measured baseline seconds per bar INCLUDING the per-call term, and `call_fixed_s` is added again per call (and per spawned worker), so index shards are slightly over-estimated (by at most ~1-2 min per shard); kept on purpose.
* **Position average (Wyckoff metals).** From 6-8 one-year slices; the per-slice cost varies 0.41-1.36 ms/bar at 1m (a +/-15 % uncertainty on the mean). The indices use the last-year (maximal-prefix) cost, which is conservative.
* **Wave 2 (about 70 % of the runner-hours).** 8 real folds on three cell shapes; the 1m cells and the 9-17-fold cells were not measured (their per-fold count is the same measured mean; a de-duplication across many folds would lower it, the audit's zero-edge counts suggest 8.7-10.8 for ICT). Treat the wave-2 sizes as +/-25 %.
* **Noise** +/-10-20 % per measurement on a shared machine (3.1).
* **The owner's 2.4 h run is not reproduced.** The model puts 39 ICT sets of XAUUSD 1m wave 1 at ~5 CPU-hours, i.e. ~1.2 h on 5 effective workers; the owner measured 2.41 h on a (memory-clamped) machine running other work, before the speed-ups. I cannot explain the 2x; it is a warning that the model could be optimistic, which the factor 2.0 layout partly covers.
* **Not modelled:** artifact upload/download time (assumed inside `job_fixed_s`), runner start queueing, `evaluate`'s statistics (modelled as the wave-2 replay; measured < 0.1 s per fold here) and the `report` job.
* **Indices:** ICT rates measured on US500 (+ US30 at 1m); Wyckoff rates measured on US500 (+ US30 at 1m). The other three index symbols were not measured (the trade-rate audit's per-symbol seconds for the S3 year, `docs/audits/2026-10-01-trade-rates.md`, show them within 10 % of US500 for ICT at 1m (227-251 s) and 0.9-1.3x for Wyckoff at 1m (125-189 s vs 143 s), measured under load with simulate included).
* **Wave-2 memory** (held trades ~1 KB each) is an estimate.

## 8. Findings outside the brief

**A. `trades_for` raises on the real ICT 1m cells (important for the pre-registration).** `scripts/research/shard_calibration.py job '{"kind":"entry_eq_stop", ...}'` over the 27 wave-1 sets of the S3 year:

| run (S3 year, one symbol) | value set | raw trades | trades with entry == stop |
|---|---|---|---|
| ICT XAUUSD 1m, all 27 wave-1 sets | `B-EX = fill` | 2,845 | 1 (long, 2023-03-09T04:40Z) |
| ICT US500 1m, all 27 wave-1 sets | `B-EX = fill` | 3,633 | 80 |
| ICT XAUUSD 1m, the other 26 sets | all | 179-2,898 over the 27 sets | 0 |
| ICT US500 1m, the other 26 sets | all | 313-3,678 over the 27 sets | 0 |
| Wyckoff US500 1m, all 14 wave-1 sets | all | 431-548 | 0 |
| ICT XAUUSD / US500 5m and 15m, `B-EX = fill` only | `B-EX = fill` | 372 / 474 (5m), 122 / 132 (15m) | 0 |

Only `B-EX = fill`, only on 1m in the S3 year (5m and 15m: 0 trades in that year; other years, the other symbols and the other wave-1 sets of the 5m/15m cells were not scanned for this, so absence there is not shown). `BtEngine.trades_for` builds the admission rows with `real_costs.cost_r(entry, stop, ...)`, which raises `CostRefused("stop distance is zero: entry and stop are the same price.")`. In a `run`, that exception is
recorded as "FAILING LOUD" for the whole candidate, so the 1m-metals and 1m-indices ICT cells cannot complete as long as `B-EX = fill` is in the grid. The raw scans (and therefore the Actions shards) are not affected; the failure appears in `evaluate`/`run`. The trade is a real engine output (`entry == stop`, long, outcome loss), not an artifact of the slice cut.
**This needs an owner decision** (engine fix behind an `fx_` key, a refusal-to-trade rule for a zero stop, or dropping the value) before `declare`; I did not change the engine or the grid. Reproduction: the job above (1m XAUUSD S3: ~25 min for 27 sets) or `entry_eq_stop` with `"sets":["w1:2"]` (the `B-EX = fill` set).
A fix inside `scripts/backtest-methods.py` would change the code fingerprint and any scan made before it.

**B. New symbols had no `DEV_BARS` rows.** The 3-cell plan needs XPTUSD and XPDUSD at 5m: measured PIT-truncated counts 494,217 and 480,765 (first bars 2015-01-06) were added, a test now asserts every symbol of every declared cell has a row (the synthetic-row monkeypatch in the test fixture was removed), and `cell_bars` fails with a message naming the missing row instead of a bare `KeyError`. For any further symbol: run
`python3 scripts/research/shard_calibration.py job '{"kind":"bars","symbols":["<SYMBOL>"],"tfs":["1m","5m","15m"]}'` on the real data. It loads each PIT-truncated series (`bt.pit_cutoff(DEV_CUTOFF)`, then `bt.load`)
and prints `bars`, `first_bar` and the committed `DEV_BARS` value; paste the `bars` into the `DEV_BARS` dict (`1m`/`5m`/`15m` -> symbol -> count) of `scripts/fund-search.py`. The same job reproduced all 21 existing rows exactly (`bars-check.json`), so the audit's table and this method agree. The group rates for the new symbols are not measured: the model would use the metals/indices
rate of the symbol's asset class; for a precision beyond that, measure one baseline slice per new symbol with the `scan` job. If a new symbol's cell sets `dev_start`, `cell_bars` already scales by the kept share of the span.

## 9. Evidence

* Raw rows: `docs/audits/2026-10-01-shard-calibration-data/res-{A,B,C,D,E,F,G,H,Z}.jsonl` (A baselines, B position spread, C/D marginal designs, E wave 2 + fixed costs + span linearity, F worker scaling, G long-span linearity, H wave-2 groups, Z zero-stop), `fit.json`, `bars-check.json`.
* Reproduce: `python3 scripts/research/shard_calibration.py job '<spec>'` (one measurement) or `drive --jobs FILE --out FILE --workers N` (N <= 4); fit: `python3 scripts/research/shard_calibration_fit.py --rows docs/audits/2026-10-01-shard-calibration-data/res-*.jsonl`.
* Layout: `python3 scripts/fund-search.py list-scan-shards [--wave 1|2] [--explain]` (needs `plan.json`; `plan` writes it, do not commit it). Summary at the three factors: `shard_summary(plan, rows)` / `format_shard_summary`.
* Tests (`scripts/tests/test_fund_search.py`, `ShardLayout`, `ShardGroupModel`): the shard-size cap at the layout factor recomputed from the model for a spread of shards, the layout follows the factor and scales exactly with it, every wave is partitioned exactly by its slices, wave-2 group estimate bounds, the measured/assumed split, the DEV_BARS refusal,
  the summary at all factors, and the data-free detection groups equal to what `scan_many` really groups by (real scans, ICT and Wyckoff).

## 9. Hosted-runner benchmark and the layout factor (recorded 2026-10-02)

MEASURED on a GitHub-hosted `ubuntu-latest` runner (Linux x86_64 azure, Python 3.12.14, `cpu_count` 4), workflow run
36941990528 (`fund-search-benchmark`, ref `windows-migration`, 7 min 49 s), raw artifact committed unmodified as
`docs/audits/2026-10-01-runner-benchmark.json`. Factor = runner seconds / reference-machine (Apple M3 Pro) seconds:

| job | reference s | runner s | factor |
|---|---:|---:|---:|
| ICT 5m XAUUSD, 1 worker | 85.4 | 134.3 | 1.57 |
| Wyckoff 5m XAUUSD, 1 worker | 21.9 | 44.4 | 2.03 |
| load of the 1m XAUUSD series | 9.3 | 16.2 | 1.74 |
| ICT 5m XAUUSD, 4 workers | 28.1 | 79.8 | 2.84 |
| Wyckoff 5m XAUUSD, 4 groups, 4 workers | 44.5 | 117.4 | 2.64 |

Reading: a single process is 1.6-2.0x slower than the reference machine, but the 4-worker jobs are 2.6-2.8x slower: a
4-vCPU hosted runner is 2 physical cores (hyper-threads), so the parallel speed-up is about 1.7x, not the reference's 2.77x.
The artifact's own `layout_factor` field (2.25) used the single-process rule only; because the shards run with 4 workers
(every cell except 1m-metals) the layout factor is DERIVED from ALL jobs: worst factor 2.84 rounded up to 0.25 = **3.0**.
`runner_benchmark_status()` now derives it from the artifact's `factors` list, and `runner_benchmark.py` uses the same rule
for future runs. `SHARD_MODEL["layout_factor"]` = 3.0, `report_factors` = (1.0, 2.0, 3.0).

Layout for the declared 3-cell plan at layout factor 3.0 (MODEL; 5 measured jobs on one runner, one date):
289 shards (62 wave 1 + 227 wave 2; each wave's matrix is below GitHub's 256-job limit), none over the 300-minute cap
at factor 3.0, longest shard 294 min, 1031 modelled runner-hours (factor 1.0: 362 h, factor 2.0: 698 h; real runs should cost
between the factor-2.0 and factor-3.0 figures: the 1-worker shards, which carry most hours, were measured at 1.6-2.0),
critical path with unlimited concurrent jobs about 10 h at factor 3.0 (7 h at factor 2.0). With a free-plan limit of 20
concurrent jobs (NOT verified for this repository) the wall time is bounded below by runner-hours / 20: about 35-52 h.
Where the hours go: 1m-metals is 252 of 289 shards and 970 of 1031 hours (ICT 385 h, Wyckoff 585 h).
Not measured: other hosted-runner instances (speed varies by host), 1m scans on a runner (the 1m series load only), jobs
under concurrent load, GitHub queueing.
