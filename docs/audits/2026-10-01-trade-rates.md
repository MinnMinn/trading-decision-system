# Trade rates per cell, to size each cell's history span (2026-10-01): COUNTS ONLY

Purpose: convert the model requirement "pooled TEST trades >= n_req" into years of TEST history per fund-search cell.
**Only trade counts, bars scanned and seconds are measured, recorded or printed. No performance figure of any kind was read
(a grep of the run logs, results and report for the performance-metric terms returned 0 hits).** Nothing is evaluated, selected, sealed or declared; no
window is proposed on the basis of any performance.

Script: `scripts/research/trade_rates.py` (`run`, `job`, `coverage`, `report`). Raw results: `/tmp/b10-results.jsonl`
(168 rows, all status OK), coverage `/tmp/b10-coverage.json`, run log `/tmp/b10-run.log`, coverage log `/tmp/b10-cov.log`.
Repo base `windows-migration` 6e14cc2, branch `b10-trade-rates`.

## Method (OBSERVED)
- Engine path: the harness's own `BtEngine(grid.runnable(), runner_method, tf, [symbol]).trades_for(grid.baseline())` of
  `scripts/fund-search.py`, unmodified: `scan_many` -> `checked_simulate` (min_rr 2.5 = `bt.OPTS["min_rr"]`, real FTMO costs,
  profile `ftmo_demo_2026_09`, `live_parity_sizing=False`, flat-before-rollover with the FTMO provider, all
  `ADOPTED_F_KEYS` incl. `fx_w7_htf_target` and `fx_admission_entry_cost`, no V overlay: the grid's first value of every
  item, `B4`/`W4b` excluded as in `runnable()`). PIT cutoff `2024-03-01` unchanged.
- Slices: S1 = 2021-03-01..2022-03-01, S2 = 2022-03-01..2023-03-01, S3 = 2023-03-01..2024-03-01 (last dev year = the
  final test fold). The decision-timeframe series of the ONE (symbol, tf) being scanned is cut (by wrapping `bt.load`;
  other timeframes such as HTF reads are untouched) to `[slice start - 14 days - scan window, slice end + 5 days]`; the
  scan window is the method's own (ICT `lr.scan_spec(tf)` bars 360/576/576/480 for 1m/5m/15m/30m; Wyckoff window 300).
  Only trades whose `entry_time` lies in `[slice start, slice end)` are counted.
- Equivalence check (OBSERVED): for US500 30m the sliced counts equal the counts of the same engine run over the whole
  PIT-truncated series with entries bucketed into the same slices: ICT 9/11/9, Wyckoff 4/2/3 (S1/S2/S3), exactly.
  Not checked for other (symbol, tf): slicing gives the same answer only if simulate()'s admission state is identical
  after warm-up, which held here.
- Workers: 4 concurrent OS processes (one per (method, symbol, tf, slice) job, each `scan_many` with `workers=1`, i.e.
  in-process), on a shared 12-core / 36 GiB machine. The pooled `scan_many` chunk pool was not used: its spawned workers
  reload the full series from disk and would bypass the slice cut. Wall time of the whole run about 52 min; sum of
  per-run seconds 3.28 h. Longest single run 541 s (Wyckoff XAUUSD 1m S2), far below the 60 min bailout; no run was
  stopped or skipped.
- `seconds` are wall seconds of one run (engine construction + scan + simulate) under 3 other concurrent runs; they
  include the warm-up/forward bars. `bars scanned` (S1 column) = bars of the cut series.

## Data coverage caveat (OBSERVED, `/tmp/b10-coverage.json`)
Index history is sparse before about mid/late 2021 although the first bar is 2017-12-27: in S1 four of five index symbols
have far fewer bars than in S2/S3 (e.g. DE40 1m: 61 602 / 344 588 / 340 328 in-slice bars for S1/S2/S3; US500 30m
8 663 / 11 777 / 11 876; US30 is complete in all three). Index S1 counts are therefore LOWER BOUNDS (partial year) and
are marked `S1*` in the tables. The derived index rates use S2 and S3 only; metals (all slices complete, `first_bar`
2004/2012) use all three. Consequence: the indices' 4 "folds" of the current plan rest on data that is partly sparse
in the earliest fold; the plan's geometry counts from the first bar.

## Results

#### ICT: admitted trades per one-year slice, bars scanned (incl. warm-up + forward), seconds per run

| cell | symbol | S1 trades | S2 trades | S3 trades | in-slice bars S1/S2/S3 | bars scanned S1 | S1 s | S2 s | S3 s |
|---|---|---|---|---|---|---|---|---|---|
| 1m-metals | XAUUSD | 408 | 411 | 407 | 352467/350433/352245 | 371707 | 238 | 239 | 231 |
| 1m-metals | XAGUSD | 258 | 295 | 248 | 350630/348564/347128 | 369779 | 265 | 268 | 264 |
| **1m-metals** | **pooled** | **666** | **706** | **655** | | | | | |
| 1m-indices | US500 | 147 | 361 | 338 | 164282/347712/339312 S1* | 170273 | 117 | 251 | 251 |
| 1m-indices | US30 | 425 | 448 | 388 | 354703/349295/351678 | 374029 | 238 | 233 | 231 |
| 1m-indices | USTEC | 171 | 427 | 397 | 164297/349363/352294 S1* | 170288 | 110 | 236 | 227 |
| 1m-indices | DE40 | 77 | 431 | 331 | 61602/344588/340328 S1* | 67367 | 48 | 245 | 234 |
| 1m-indices | FRA40 | 141 | 312 | 266 | 164481/329424/306229 S1* | 170476 | 119 | 245 | 227 |
| **1m-indices** | **pooled** | **961** | **1979** | **1720** | | | | | |
| 5m-metals | XAUUSD | 44 | 61 | 57 | 70635/70106/70454 | 74996 | 78 | 81 | 79 |
| 5m-metals | XAGUSD | 52 | 66 | 57 | 70466/69995/70421 | 74816 | 85 | 91 | 88 |
| **5m-metals** | **pooled** | **96** | **127** | **114** | | | | | |
| 5m-indices | US500 | 30 | 59 | 72 | 35487/69877/70432 S1* | 37370 | 43 | 86 | 82 |
| 5m-indices | US30 | 62 | 65 | 76 | 70962/69880/70475 | 75332 | 81 | 82 | 77 |
| 5m-indices | USTEC | 23 | 69 | 88 | 35448/69880/70476 S1* | 37331 | 43 | 86 | 81 |
| 5m-indices | DE40 | 14 | 69 | 71 | 15563/69928/69053 S1* | 17233 | 20 | 84 | 79 |
| 5m-indices | FRA40 | 34 | 56 | 45 | 35535/69294/68211 S1* | 37422 | 43 | 86 | 83 |
| **5m-indices** | **pooled** | **163** | **318** | **352** | | | | | |
| 15m-metals | XAUUSD | 12 | 18 | 15 | 23719/23622/23739 | 25564 | 26 | 28 | 27 |
| 15m-metals | XAGUSD | 18 | 20 | 23 | 23701/23584/23735 | 25544 | 29 | 31 | 30 |
| **15m-metals** | **pooled** | **30** | **38** | **38** | | | | | |
| 15m-indices | US500 | 14 | 18 | 21 | 14098/23544/23745 S1* | 15264 | 18 | 30 | 28 |
| 15m-indices | US30 | 18 | 16 | 24 | 23775/23544/23747 | 25620 | 28 | 29 | 27 |
| 15m-indices | USTEC | 17 | 23 | 14 | 14087/23544/23747 S1* | 15253 | 18 | 31 | 29 |
| 15m-indices | DE40 | 6 | 24 | 22 | 7699/23567/23283 S1* | 8649 | 10 | 29 | 27 |
| 15m-indices | FRA40 | 17 | 15 | 23 | 14092/23449/23328 S1* | 15262 | 18 | 30 | 29 |
| **15m-indices** | **pooled** | **72** | **96** | **104** | | | | | |
| 30m-metals | XAUUSD | 1 | 11 | 7 | 11871/11815/11871 | 12986 | 11 | 12 | 12 |
| 30m-metals | XAGUSD | 2 | 8 | 8 | 11873/11797/11869 | 12988 | 12 | 13 | 13 |
| **30m-metals** | **pooled** | **3** | **19** | **15** | | | | | |
| 30m-indices | US500 | 9 | 11 | 9 | 8663/11777/11876 S1* | 9551 | 9 | 13 | 12 |
| 30m-indices | US30 | 9 | 17 | 13 | 11890/11777/11876 | 13005 | 12 | 12 | 12 |
| 30m-indices | USTEC | 12 | 10 | 15 | 8660/11777/11876 S1* | 9548 | 9 | 13 | 12 |
| 30m-indices | DE40 | 1 | 6 | 9 | 5707/11791/11644 S1* | 6379 | 6 | 12 | 11 |
| 30m-indices | FRA40 | 11 | 14 | 4 | 8640/11733/11680 S1* | 9532 | 9 | 12 | 12 |
| **30m-indices** | **pooled** | **42** | **58** | **50** | | | | | |

#### WYCKOFF: admitted trades per one-year slice, bars scanned (incl. warm-up + forward), seconds per run

| cell | symbol | S1 trades | S2 trades | S3 trades | in-slice bars S1/S2/S3 | bars scanned S1 | S1 s | S2 s | S3 s |
|---|---|---|---|---|---|---|---|---|---|
| 1m-metals | XAUUSD | 138 | 281 | 207 | 352467/350433/352245 | 371647 | 314 | 541 | 514 |
| 1m-metals | XAGUSD | 150 | 306 | 264 | 350630/348564/347128 | 369719 | 265 | 438 | 449 |
| **1m-metals** | **pooled** | **288** | **587** | **471** | | | | | |
| 1m-indices | US500 | 102 | 260 | 200 | 164282/347712/339312 S1* | 170213 | 59 | 129 | 143 |
| 1m-indices | US30 | 242 | 266 | 229 | 354703/349295/351678 | 373969 | 155 | 166 | 189 |
| 1m-indices | USTEC | 142 | 302 | 300 | 164297/349363/352294 S1* | 170228 | 54 | 122 | 141 |
| 1m-indices | DE40 | 46 | 278 | 197 | 61602/344588/340328 S1* | 67307 | 23 | 118 | 126 |
| 1m-indices | FRA40 | 96 | 226 | 168 | 164481/329424/306229 S1* | 170416 | 57 | 120 | 125 |
| **1m-indices** | **pooled** | **628** | **1332** | **1094** | | | | | |
| 5m-metals | XAUUSD | 52 | 58 | 63 | 70635/70106/70454 | 74720 | 30 | 32 | 31 |
| 5m-metals | XAGUSD | 43 | 62 | 60 | 70466/69995/70421 | 74540 | 28 | 30 | 31 |
| **5m-metals** | **pooled** | **95** | **120** | **123** | | | | | |
| 5m-indices | US500 | 26 | 62 | 51 | 35487/69877/70432 S1* | 37094 | 11 | 22 | 22 |
| 5m-indices | US30 | 53 | 63 | 54 | 70962/69880/70475 | 75056 | 23 | 22 | 23 |
| 5m-indices | USTEC | 31 | 61 | 40 | 35448/69880/70476 S1* | 37055 | 11 | 21 | 21 |
| 5m-indices | DE40 | 7 | 49 | 51 | 15563/69928/69053 S1* | 16957 | 5 | 22 | 21 |
| 5m-indices | FRA40 | 24 | 49 | 35 | 35535/69294/68211 S1* | 37146 | 11 | 22 | 21 |
| **5m-indices** | **pooled** | **141** | **284** | **231** | | | | | |
| 15m-metals | XAUUSD | 25 | 22 | 19 | 23719/23622/23739 | 25288 | 9 | 10 | 9 |
| 15m-metals | XAGUSD | 25 | 24 | 21 | 23701/23584/23735 | 25268 | 9 | 9 | 9 |
| **15m-metals** | **pooled** | **50** | **46** | **40** | | | | | |
| 15m-indices | US500 | 11 | 21 | 19 | 14098/23544/23745 S1* | 14988 | 4 | 7 | 7 |
| 15m-indices | US30 | 22 | 23 | 19 | 23775/23544/23747 | 25344 | 8 | 7 | 7 |
| 15m-indices | USTEC | 5 | 20 | 26 | 14087/23544/23747 S1* | 14977 | 4 | 7 | 7 |
| 15m-indices | DE40 | 5 | 18 | 16 | 7699/23567/23283 S1* | 8373 | 2 | 7 | 7 |
| 15m-indices | FRA40 | 8 | 12 | 11 | 14092/23449/23328 S1* | 14986 | 4 | 7 | 7 |
| **15m-indices** | **pooled** | **51** | **94** | **91** | | | | | |
| 30m-metals | XAUUSD | 10 | 5 | 3 | 11871/11815/11871 | 12806 | 4 | 4 | 4 |
| 30m-metals | XAGUSD | 5 | 4 | 5 | 11873/11797/11869 | 12808 | 4 | 4 | 4 |
| **30m-metals** | **pooled** | **15** | **9** | **8** | | | | | |
| 30m-indices | US500 | 4 | 2 | 3 | 8663/11777/11876 S1* | 9371 | 3 | 3 | 3 |
| 30m-indices | US30 | 3 | 3 | 4 | 11890/11777/11876 | 12825 | 4 | 3 | 3 |
| 30m-indices | USTEC | 3 | 4 | 6 | 8660/11777/11876 S1* | 9368 | 2 | 3 | 3 |
| 30m-indices | DE40 | 0 | 6 | 5 | 5707/11791/11644 S1* | 6199 | 2 | 3 | 3 |
| 30m-indices | FRA40 | 1 | 7 | 5 | 8640/11733/11680 S1* | 9352 | 3 | 4 | 3 |
| **30m-indices** | **pooled** | **11** | **22** | **23** | | | | | |

`*` after a slice = that symbol's in-slice bars are < 90 % of its best-covered slice (partial data; its count is a lower bound).

#### Derived years of TEST history (MODEL)

rate = mean pooled trades/yr over the slices in which EVERY symbol of the cell is fully covered (all three for metals). years = n_req / rate; 2x = design effect 2. test folds needed = max(2, ceil(years)); min total span = 2 (training >= 730 d) + test folds needed.

| method | cell | slices used | pooled S1/S2/S3 | rate /yr | n_req | years (1x) | years (2x) | test folds now | expected TEST trades now | >= n_req? | >= 2x n_req? | min total span yrs (1x / 2x) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ict | 1m-metals | S1,S2,S3 | 666/706/655 | 675.7 | 760 | 1.1 | 2.2 | 9 | 6081 | yes | yes | 4 / 5 |
| ict | 1m-indices | S2,S3 | 961/1979/1720 | 1849.5 | 760 | 0.4 | 0.8 | 4 | 7398 | yes | yes | 4 / 4 |
| ict | 5m-metals | S1,S2,S3 | 96/127/114 | 112.3 | 760 | 6.8 | 13.5 | 17 | 1910 | yes | yes | 9 / 16 |
| ict | 5m-indices | S2,S3 | 163/318/352 | 335.0 | 760 | 2.3 | 4.5 | 4 | 1340 | yes | no | 5 / 7 |
| ict | 15m-metals | S1,S2,S3 | 30/38/38 | 35.3 | 760 | 21.5 | 43.0 | 17 | 601 | no | no | 24 / 46 |
| ict | 15m-indices | S2,S3 | 72/96/104 | 100.0 | 760 | 7.6 | 15.2 | 4 | 400 | no | no | 10 / 18 |
| ict | 30m-metals | S1,S2,S3 | 3/19/15 | 12.3 | 760 | 61.6 | 123.2 | 17 | 210 | no | no | 64 / 126 |
| ict | 30m-indices | S2,S3 | 42/58/50 | 54.0 | 760 | 14.1 | 28.1 | 4 | 216 | no | no | 17 / 31 |
| wyckoff | 1m-metals | S1,S2,S3 | 288/587/471 | 448.7 | 690 | 1.5 | 3.1 | 9 | 4038 | yes | yes | 4 / 6 |
| wyckoff | 1m-indices | S2,S3 | 628/1332/1094 | 1213.0 | 690 | 0.6 | 1.1 | 4 | 4852 | yes | yes | 4 / 4 |
| wyckoff | 5m-metals | S1,S2,S3 | 95/120/123 | 112.7 | 690 | 6.1 | 12.2 | 17 | 1915 | yes | yes | 9 / 15 |
| wyckoff | 5m-indices | S2,S3 | 141/284/231 | 257.5 | 690 | 2.7 | 5.4 | 4 | 1030 | yes | no | 5 / 8 |
| wyckoff | 15m-metals | S1,S2,S3 | 50/46/40 | 45.3 | 690 | 15.2 | 30.4 | 17 | 771 | yes | no | 18 / 33 |
| wyckoff | 15m-indices | S2,S3 | 51/94/91 | 92.5 | 690 | 7.5 | 14.9 | 4 | 370 | no | no | 10 / 17 |
| wyckoff | 30m-metals | S1,S2,S3 | 15/9/8 | 10.7 | 690 | 64.7 | 129.4 | 17 | 181 | no | no | 67 / 132 |
| wyckoff | 30m-indices | S2,S3 | 11/22/23 | 22.5 | 690 | 30.7 | 61.3 | 4 | 90 | no | no | 33 / 64 |


## Reading the derived table (MODEL, not measurement)
- n_req = 760 (ICT, N=232) / 690 (Wyckoff, N=128) and the design-effect-2 variant 2 x n_req are the coordinator's model
  (binary +2.5/-1 outcomes, 0.20R edge, iid lower bound; cluster-robust 1.5-3x). They are assumptions, not measured here.
- "expected TEST trades now" = mean pooled trades per year x the number of test folds the plan gives the cell (metals 1m
  9, metals 5m/15m/30m 17, all indices cells 4; from `plan --dry-run`; one fold = 365 days). It assumes the 2021-2023
  rate also holds in the earlier folds: for the metals folds (2004/2012 onward) that is an EXTRAPOLATION, not measured.
  The year-to-year spread inside the three slices is visible in the "pooled S1/S2/S3" column (e.g. ICT 30m metals 3/19/15,
  Wyckoff 1m metals 288/587/471), so the rate itself is uncertain by far more than the decimals suggest.
- "min total span" = 2 years of training (>= 730 d) + max(2, ceil(years)) test folds; the structural minimum of the plan
  is 4 years (2 + 2). Cells with years <= 2 are bound by the structural minimum, not by n_req.
- Cells whose current fold count already reaches n_req (1x): 1m-metals, 1m-indices, 5m-metals, 5m-indices for both methods,
  plus Wyckoff 15m-metals. At 2x n_req the "no" cells are: ICT and Wyckoff 5m-indices (4 folds give 1340/1030 expected
  vs 1520/1380 needed) and Wyckoff 15m-metals (771 vs 1380). Cells short even at 1x: ICT 15m-metals (601 vs 760 with 17
  folds), 15m-indices, 30m-metals, 30m-indices, and Wyckoff 15m-indices, 30m-metals, 30m-indices.
- Cells short at 1x need the following years of TEST history at the measured rate (from the table): ICT 15m-metals 21.5,
  ICT 15m-indices 7.6, ICT 30m-metals 61.6, ICT 30m-indices 14.1; Wyckoff 15m-indices 7.5, 30m-metals 64.7,
  30m-indices 30.7. Where that exceeds the available history (metals 5m-30m 17 folds from 2004, metals 1m 9 folds from 2012; indices
  from 2017-12, 4 folds), the cell cannot reach n_req by lengthening the window; this table does not recommend what to do
  about it.
- Limits of these counts: one baseline value set only (V overlays that add trades would raise the rate and were out of
  scope); pooled across a cell's symbols by plain summation (overlapping signals across correlated symbols are NOT
  de-duplicated, which is the cluster effect the 2x column is meant to stand in for); counts, not independence.

## Reproduce
```
BT_HISTORY_ROOT=data/history/ftmo python3 scripts/research/trade_rates.py run --out /tmp/b10-results.jsonl --workers 4
BT_HISTORY_ROOT=data/history/ftmo python3 scripts/research/trade_rates.py coverage --out /tmp/b10-coverage.json
python3 scripts/research/trade_rates.py report --in /tmp/b10-results.jsonl --cov /tmp/b10-coverage.json
```
