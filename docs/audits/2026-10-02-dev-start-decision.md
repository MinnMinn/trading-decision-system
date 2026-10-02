# dev_start decisions by the availability rule (2026-10-02)

Status: decided by a rule stated before looking (draft section 0.3, owner approved 2026-10-02 for `5m-metals`). Inputs are
admitted-trade COUNTS and bar COUNTS only. No trade outcome or performance figure was read, computed or stored by any step
(checked by a text search for the outcome-metric terms over the scripts, logs and files listed here: no hits).

## 0. Disclosure of the extension to 1m-indices

The owner approved the rule for `5m-metals` only. The coordinator extended the SAME principle to `1m-indices` after the
engine-realism census (`docs/audits/2026-10-02-engine-realism-census.md`) showed the same availability problem there: US500,
USTEC and FRA40 have about 260 bars per year until 2021-09, DE40 is dense only from 2022-01, US30 from 2019-02. The
extension, and the added dense-symbol condition below, were fixed before any count of this round was read and before any
outcome was seen. The owner may overrule the extension; the `1m-indices` decision then reverts to `dev_start = null`
(4 folds) and `plan_hash` changes again.

## 1. Rule as applied

For each candidate start (earliest first), P = probability that EVERY test fold reaches `MIN_FOLD_TRADES = 30` admitted
trades, for BOTH methods, under the availability-aware model of `docs/audits/2026-10-01-cell-selection.md` (T3-avail).
Take the earliest candidate with P >= 0.80 for both methods; if none qualifies take the last candidate.

- Candidates: `5m-metals` {2004-06-11 (17 folds), 2009-03-01 (13), 2015-01-07 (7)}; `1m-indices` {2017-12-27 (4), 2020-03-01 (2)}.
  Fold counts reproduced with `scripts/research/dev_start_decision.py` (`folds_for`, the `make_folds` geometry): 17 / 13 / 7 / 4 / 2.
- Added condition (`1m-indices` only, stated before looking): a start is admissible only if in EVERY test fold at least
  `ceil(2m/3) = 4` of the 5 symbols have DENSE data in that fold OR in the preceding training window `[start, fold start)`.
  Dense = total bars of the window >= 50 % of the expected bars (per-weekday bar count of the symbol in the reference
  year 2023-03..2024-02 times the weekdays of the window's months; a symbol with no bars is not dense).
- If no candidate satisfies both conditions the facts go to the owner; not the case here.
- Counts: `scripts/research/trade_rates.py run --year-cells 1m-indices 5m-metals` (one-calendar-year slices `Y<year>`, the harness
  engine as merged: relative-spread real costs, `min_rr` 2.5, fx gap-fill, zero-risk refusal, O1 admission under the fixed
  OPTS, baseline value set, 14-day warm-up, 5-day forward walk). First (partial) year of a symbol: the scan starts at its first
  bar (`allow_partial`; a lower bound). 174 jobs, 4 processes, none NOT MEASURED. Raw results:
  `docs/audits/2026-10-02-dev-start-counts.jsonl`; bar counts per symbol-month: `docs/audits/2026-10-02-dev-start-density.json`.
- Model: `scripts/research/dev_start_decision.py decide`: `power_model` machinery (month-level lognormal regime sigma 0.75,
  weekday-only Poisson arrivals, cross-symbol correlation rho 0.3, seed `power_model.seed_for("dev-start|<cell>|<start>|<method>|<mode>", folds, k, rho)`
  with `BASE_SEED` 20261001), 2000 replications per (cell, start, method, mode). The per-symbol rate of each test fold is its
  measured admitted-trade count for the fold's calendar years (pro rata by days); a symbol with no bars before its first bar has
  count 0, i.e. it is absent. The rho-0.3 discount follows the cell-selection doc (`k_eff = k / (1 + (k-1) rho)` applied to the
  sum): mode `cell` (PRIMARY, the T3-avail convention: the cell's full k, 4 for 5m-metals) and mode `present` (SENSITIVITY: k of
  the symbols with trades in that fold). `gen_stream` itself is not modified; a per-fold-rate variant sits in the new script
  (`gen_stream_by_fold`). The synthetic edge only affects synthetic wins, never a per-fold trade count.
- Approximation, disclosed: folds are 365-day blocks, counts are calendar years; a fold's count is the pro-rata sum.

## 2. Result

Chosen starts (primary model): `5m-metals` **2015-01-07** (7 folds), `1m-indices` **2020-03-01** (2 folds). 1m-metals is not
part of this decision and stays `null` (9 folds).

CONCERN for the owner (5m-metals): the verdict depends on the discount convention. Under the pre-stated primary convention
(T3-avail: full-cell k) the 2009-03-01 candidate fails for ICT (P 0.735 < 0.80). Under the `present`-symbols sensitivity
convention 2009-03-01 passes both methods (ICT 0.923, Wyckoff 0.980) and would win (13 folds). The primary convention is the one
the rule names (the existing availability-aware model); it was not changed after seeing this. 2004-06-11 fails under both
conventions (Wyckoff 0.101 / 0.559).

### T1. Admitted baseline trades per symbol, method and calendar year (counts only)


**5m-metals** (`-` = no bars that year)

| method | symbol | 2004 | 2005 | 2006 | 2007 | 2008 | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ict | XAUUSD | 20 | 29 | 94 | 77 | 94 | 98 | 67 | 59 | 52 | 46 | 34 | 57 | 58 | 52 | 52 | 50 | 53 | 46 | 65 | 51 |
| ict | XAGUSD | - | - | - | - | 6 | 12 | 14 | 52 | 62 | 43 | 35 | 37 | 41 | 32 | 30 | 31 | 54 | 47 | 72 | 64 |
| ict | XPTUSD | - | - | - | - | - | - | - | - | - | - | - | 0 | 2 | 9 | 17 | 15 | 45 | 25 | 40 | 32 |
| ict | XPDUSD | - | - | - | - | - | - | - | - | - | - | - | 1 | 2 | 15 | 23 | 23 | 49 | 27 | 50 | 33 |
| wyckoff | XAUUSD | 7 | 28 | 44 | 38 | 57 | 73 | 53 | 58 | 55 | 43 | 42 | 35 | 50 | 48 | 37 | 51 | 48 | 44 | 60 | 62 |
| wyckoff | XAGUSD | - | - | - | - | 5 | 47 | 36 | 61 | 52 | 58 | 49 | 54 | 44 | 45 | 44 | 32 | 48 | 38 | 67 | 53 |
| wyckoff | XPTUSD | - | - | - | - | - | - | - | - | - | - | - | 2 | 4 | 29 | 29 | 44 | 45 | 32 | 57 | 49 |
| wyckoff | XPDUSD | - | - | - | - | - | - | - | - | - | - | - | 0 | 0 | 30 | 29 | 38 | 39 | 27 | 40 | 40 |

**1m-indices** (`-` = no bars that year)

| method | symbol | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---|---|---|---|---|---|---|---|
| ict | US500 | 0 | 0 | 0 | 0 | 85 | 390 | 362 |
| ict | US30 | - | - | 308 | 404 | 416 | 451 | 426 |
| ict | USTEC | 0 | 0 | 0 | 0 | 112 | 433 | 433 |
| ict | DE40 | 0 | 0 | 0 | 1 | 7 | 449 | 361 |
| ict | FRA40 | 0 | 0 | 0 | 1 | 82 | 341 | 264 |
| wyckoff | US500 | 0 | 0 | 0 | 0 | 75 | 254 | 198 |
| wyckoff | US30 | - | - | 172 | 279 | 252 | 267 | 242 |
| wyckoff | USTEC | 0 | 0 | 0 | 0 | 91 | 317 | 306 |
| wyckoff | DE40 | 0 | 0 | 0 | 0 | 2 | 287 | 201 |
| wyckoff | FRA40 | 0 | 0 | 0 | 0 | 69 | 226 | 179 |

### T2. Bar counts per symbol-year (full per-month table: `docs/audits/2026-10-02-dev-start-density.json`)


**5m-metals**; expected bars/weekday (reference 2023-03..2024-02) in the last column

| symbol | first bar | 2004 | 2005 | 2006 | 2007 | 2008 | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | exp/weekday |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| XAUUSD | 2004-06-11 | 28408 | 51717 | 56015 | 64111 | 68165 | 68321 | 64429 | 65596 | 66496 | 70077 | 70079 | 69841 | 70370 | 70070 | 70213 | 70174 | 70587 | 70427 | 70089 | 69909 | 11689 | 269 |
| XAGUSD | 2008-11-07 | 0 | 0 | 0 | 0 | 8798 | 65929 | 63532 | 66334 | 66538 | 70045 | 70032 | 69759 | 70367 | 70071 | 70210 | 70178 | 70531 | 70196 | 69996 | 69893 | 11672 | 269 |
| XPTUSD | 2015-01-06 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1965 | 3880 | 54171 | 70415 | 70911 | 70836 | 70558 | 69930 | 69870 | 11681 | 269 |
| XPDUSD | 2015-01-06 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2000 | 3833 | 52067 | 66071 | 69038 | 67879 | 69809 | 69650 | 68865 | 11553 | 264 |

**1m-indices**; expected bars/weekday (reference 2023-03..2024-02) in the last column

| symbol | first bar | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | exp/weekday |
|---|---|---|---|---|---|---|---|---|---|---|
| US500 | 2017-12-28 | 1 | 258 | 259 | 259 | 109335 | 348342 | 338482 | 55759 | 1295 |
| US30 | 2019-02-08 | 0 | 0 | 268871 | 350450 | 353926 | 349309 | 349090 | 58133 | 1342 |
| USTEC | 2017-12-28 | 1 | 258 | 259 | 259 | 109349 | 349364 | 349626 | 58226 | 1345 |
| DE40 | 2017-12-27 | 3 | 135 | 234 | 257 | 6746 | 344038 | 339029 | 56746 | 1299 |
| FRA40 | 2017-12-28 | 1 | 255 | 254 | 258 | 109588 | 334587 | 306010 | 50595 | 1169 |

### T3. 1m-indices: dense symbols per test fold (dense = bars >= 50 % of expected over the window)


Candidate 2017-12-27 (4 folds), need >= 4 of 5 dense in the fold OR its preceding training window [2017-12-27, fold start): **FAIL**

| fold | test window | dense in fold | dense in fold or training | ok | dense symbols in fold | dense in training |
|---|---|---|---|---|---|---|
| 1 | 2020-03-02 .. 2021-03-02 | 1 | 1 | NO | US30 | - |
| 2 | 2021-03-02 .. 2022-03-02 | 4 | 4 | yes | US500 US30 USTEC FRA40 | US30 |
| 3 | 2022-03-02 .. 2023-03-02 | 5 | 5 | yes | US500 US30 USTEC DE40 FRA40 | US30 |
| 4 | 2023-03-02 .. 2024-03-01 | 5 | 5 | yes | US500 US30 USTEC DE40 FRA40 | US30 |

Candidate 2020-03-01 (2 folds), need >= 4 of 5 dense in the fold OR its preceding training window [2020-03-01, fold start): **PASS**

| fold | test window | dense in fold | dense in fold or training | ok | dense symbols in fold | dense in training |
|---|---|---|---|---|---|---|
| 1 | 2022-03-02 .. 2023-03-02 | 5 | 5 | yes | US500 US30 USTEC DE40 FRA40 | US30 |
| 2 | 2023-03-02 .. 2024-03-01 | 5 | 5 | yes | US500 US30 USTEC DE40 FRA40 | US500 US30 USTEC FRA40 |

### T4. P(every test fold >= 30 admitted trades), 2000 replications, threshold 0.8

`cell` = the T3-avail convention (rho-0.3 discount with the cell's full k); `present` = discount with the symbols that have trades in that fold (sensitivity). Both models use the SAME seeds per (cell, start, method, mode).

| cell | candidate start | folds | ICT P (cell) | Wyckoff P (cell) | ICT P (present) | Wyckoff P (present) | both >= 0.80 | dense condition | admissible |
|---|---|---|---|---|---|---|---|---|---|
| 5m-metals | 2004-06-11 | 17 | 0.562 | 0.101 | 0.892 | 0.559 | no | n/a | no |
| 5m-metals | 2009-03-01 | 13 | 0.735 | 0.905 | 0.923 | 0.980 | no | n/a | no |
| 5m-metals | 2015-01-07 | 7 | 0.994 | 1.000 | 0.993 | 1.000 | yes | n/a | yes |
| 1m-indices | 2017-12-27 | 4 | 1.000 | 1.000 | 1.000 | 1.000 | yes | FAIL | no |
| 1m-indices | 2020-03-01 | 2 | 1.000 | 1.000 | 1.000 | 1.000 | yes | PASS | yes |

### T5. Model-expected pooled trades per fold (primary model, mean of the synthetic folds)

| cell | start | method | per fold, oldest first |
|---|---|---|---|
| 5m-metals | 2004-06-11 | ict | 42.3 53.6 55.9 45.1 58.7 57.1 45.2 38.5 50.5 54.7 58.4 63.3 69.4 101.2 84.0 115.4 78.6 |
| 5m-metals | 2004-06-11 | wyckoff | 22.2 38.2 59.6 49.3 60.8 55.6 52.6 48.4 48.9 56.5 79.1 75.2 86.6 91.4 81.5 115.8 89.5 |
| 5m-metals | 2009-03-01 | ict | 58.6 57.6 44.7 39.0 50.5 55.0 58.1 64.4 69.6 101.0 83.7 115.3 78.5 |
| 5m-metals | 2009-03-01 | wyckoff | 61.5 55.1 52.2 47.9 48.4 56.2 78.9 75.4 87.9 91.4 81.3 116.5 90.3 |
| 5m-metals | 2015-01-07 | ict | 58.3 63.7 69.7 101.2 82.8 114.7 79.6 |
| 5m-metals | 2015-01-07 | wyckoff | 78.9 75.4 87.7 91.4 81.8 115.9 89.3 |
| 1m-indices | 2017-12-27 | ict | 206.7 421.4 919.2 701.0 |
| 1m-indices | 2017-12-27 | wyckoff | 141.9 286.7 600.6 427.5 |
| 1m-indices | 2020-03-01 | ict | 924.5 702.4 |
| 1m-indices | 2020-03-01 | wyckoff | 601.4 431.2 |

### T6. Verdict

- 5m-metals: dev_start = **2015-01-07** (earliest admissible candidate)
- 1m-indices: dev_start = **2020-03-01** (earliest admissible candidate)

## 3. Span-equivalence evidence (cells-file requirement for every non-null dev_start)

`scripts/research/span_equivalence.py` (harness `BtEngine`, baseline value set, `warmup_days` 14): the run cut at `dev_start` equals
the full-series run from `dev_start`, trade by trade, over every field except the two start-dependent ones (`exit` = bar index
into the loaded series, `pnl` = dollars of the account that compounds from the run's first trade; neither is read by the fund
statistics). sha256 of the canonical JSON of the trade lists; only counts, timestamps and hashes are printed. Raw JSON:
`docs/audits/2026-10-02-dev-start-span-equivalence.json`.

| cell | method | symbol | tf | dev_start | trades full (>= dev_start) | trades cut | before dev_start in cut | differences | sha256 (start-dependent fields excluded; full = cut) | identical |
|---|---|---|---|---|---|---|---|---|---|---|
| 5m-metals | ict | XAUUSD | 5m | 2015-01-07T00:00:00Z | 496 | 496 | 0 | 0 | `17d2ee1b10173733ba48eacc99b995b620609c4b0c5dc007b49718433f619c73` | yes |
| 5m-metals | wyckoff | XAUUSD | 5m | 2015-01-07T00:00:00Z | 447 | 447 | 0 | 0 | `73a94caedbeb501d7c95e22c73066491b1addb209bd2904f0ae5b1cdb3ef2029` | yes |
| 1m-indices | ict | US500 | 1m | 2020-03-01T00:00:00Z | 896 | 896 | 0 | 0 | `6fbbb686f010e3f1a6fbaf7e9bca6a910243998897542509bb017c66c5abbe78` | yes |
| 1m-indices | wyckoff | US500 | 1m | 2020-03-01T00:00:00Z | 564 | 564 | 0 | 0 | `9e14669278e479418aebc94dc389d4fdb733fc858be180a55efc6da0178e8239` | yes (also all fields) |

Command: `BT_HISTORY_ROOT=data/history/ftmo python3 scripts/research/span_equivalence.py --method <m> --symbol <s> --tf <tf> --dev-start <iso>`.

## 4. Applied

- `docs/architecture/fund-search-cells.json`: `1m-indices` `dev_start` 2020-03-01T00:00:00Z, `5m-metals` `dev_start` 2015-01-07T00:00:00Z
  (rationale, decision, `_why`, `_warmup_days_why` updated; `1m-metals` stays null). The file is hashed into `plan_hash`.
- `python3 scripts/fund-search.py plan --dry-run`: 1m-metals 9 folds (from data), 1m-indices 2 folds (declared), 5m-metals 7 folds
  (declared). `plan.json` recommitted (no ledger declaration exists, so this is pre-declaration): `plan_hash` 12331b40583a6bd3
  (full `12331b40583a6bd3fdcf92a51a16a6341cb5c8c20e48ca5afe2da1b6edd7e63b`), previous a043358b89314982.
- Consequence for the plan, not for this decision: with 2 folds `1m-indices` has a frequency rule of 2 of 2 folds and a
  stability and power profile that the earlier 4-fold figures in `docs/audits/2026-10-01-power-model.md` and
  `docs/audits/2026-10-01-cell-selection.md` (which assumed the data start) do not describe; those audits are historical and are not edited.
  The ICT/Wyckoff model-expected pooled trades per fold of the chosen starts are in T5.
- Tests: `scripts/tests/test_fund_search.py` pins updated (committed cells: dev_starts and folds 9 / 2 / 7; the real-plan shard layout 288 = 62 + 226, was 289 = 62 + 227; first-bar mocks of three readiness tests give the metals their real 2004 first bar so the 2015 start is covered).
- Scripts: `scripts/research/dev_start_decision.py` (new), `scripts/research/trade_rates.py` (calendar-year slices `Y<year>`,
  `allow_partial`, `run --year-cells --census`; the S1..S3 behaviour is unchanged).
