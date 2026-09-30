# Engine speed: profile, changes, equivalence proof, benchmarks (2026-09-30)

Branch `b3-speed`, from `windows-migration` fef6d6b ("BASE"). Scope: make the pre-registered fund search feasible
(`scripts/fund-search.py` scores ~41 ICT / ~16 Wyckoff value sets per symbol per cell, plus perturbation sets) **without changing
any result**. Hard requirement (CLAUDE.md §40, "optimisation must not ... silently change methodology behaviour"): every
optimisation returns trades byte-identical -- same list, same fields, same order -- to BASE for the same inputs. No rule,
threshold, default or `fx_` key semantic was touched; no evaluation was run; the only numbers below are seconds, bar counts
and trade **counts** (never R or expectancy).

Machine: 12-core macOS (Darwin 25.6.0), 38.65 GB RAM, Python 3.14.5. Data: `data/history/ftmo` (tracked), `bt.pit_cutoff`
= `DEV_CUTOFF` 2024-03-01. Exact development-span bar counts (parsed from the year files, not estimated):

| tf | XAUUSD | XAGUSD | US500 | US30 | USTEC | DE40 | FRA40 |
|---|---|---|---|---|---|---|---|
| 1m | 4,096,182 | 4,097,904 | 852,695 | 1,729,779 | 867,342 | 747,188 | 801,548 |
| 5m | 1,316,783 | 1,054,081 | 177,185 | 346,651 | 177,192 | 155,214 | 174,454 |
| 15m | 453,893 | 357,694 | 62,776 | 116,405 | 62,766 | 55,219 | 62,283 |
| 30m | 229,853 | 180,535 | 33,705 | 58,257 | 33,701 | 29,812 | 33,467 |

## 1. Profile (Step 1) -- BASE, one scan

Tools: `cProfile` for function-level cost on a short slice (iteration), and a stdlib `SIGPROF` sampler (2 ms, innermost repo
frame per sample) for line-level shares on the full scans (cProfile inflates a 226 s scan ~2.3x; the sampler does not). Shares
are of the whole scan.

### ICT, US500 5m, full development span (177,185 bars, 219 s; the brief's 226 s)

| where (BASE line numbers) | share |
|---|---|
| `read_at` -> `structures.ict_analysis` -> `ict-scan.analyze()` -- the per-bar window analysis | **94-95 %** |
| &nbsp;&nbsp;swing pivots, `all(...)` generators, ict-scan.py:230-231 | 22.1 % |
| &nbsp;&nbsp;pool dedupe in `add()`, :269 (whole `add()` incl. sweep scan :288: 17.0 %) | 8.7 % |
| &nbsp;&nbsp;FVG build + mitigation scan, :239-242 | 13.3 % |
| &nbsp;&nbsp;per-window column lists / min / max / median, :219-222 | 12.6 % |
| &nbsp;&nbsp;day table (`setdefault` of a throw-away dict per bar), :438-439 | 9.0 % |
| &nbsp;&nbsp;equal-high/low pair search, :311/:314 | 4.4 % |
| &nbsp;&nbsp;`leg_disp` (displacement) | 4.1 % |
| `setup_candidate` (+ its three column lists, :570) | 2.5 % |
| everything else (`load` 0.3 %, `all_pivots` 0.1 %, gates, `walk`, `fvg_fill`) | < 3 % |

Short slice (20,000 bars, cProfile, 53.6 s): `analyze` 52.2 s = 97 %, 19,425 calls of ~2.7 ms each (cProfile-inflated); `add()` 10.3 s; the
pivot generators 10.4 s. **The setup/gate/simulate half a value set changes is ~3 % of a scan; the per-bar analysis it
re-runs for every value set is ~95 %.** Most V keys never reach `analyze()`.

### WYCKOFF-BOOK, XAUUSD 15m, full development span (453,893 bars, 202 s; the brief's 212 s)

| where (BASE line numbers) | share |
|---|---|
| `_wyckoff_candidates` -> `structures.wyckoff_records` -> `detect_accumulations` (+ `detect_distributions`, which re-runs it on inverted prices) | **93-96 %** |
| &nbsp;&nbsp;`wyckoff_rules.swings()` -- the k-bar pivot test, `all(...)` generators, wyckoff_rules.py:150-152 | 57.8 % (53.5 % in the three generator lines) |
| &nbsp;&nbsp;`lows`/`highs` list-comprehensions over all swings for every candidate SC, :265 | 20.6 % |
| &nbsp;&nbsp;`inv = lambda xs: [-x for x in xs]` (mirror side) | 2.8 % |
| &nbsp;&nbsp;`volume_profile` | 0.8 % |
| `load` 0.4 %, `all_pivots` 0.3 % | < 1 % |

Short slice (20,000 bars, cProfile, 22.4 s): `swings` 17.0 s = 76 %. Detection is the cost and it does not depend on the
gating half of OPTS; the process-local `_WY_CANDIDATES` cache already shares it between value sets that agree on the
detection keys, but each *distinct* detection group (`fx_w4a_linger_closes`, `fx_w6_window`, `fx_w_tw`, the four F keys)
pays the whole scan again.

## 2. What changed (Step 2), in the order the profile justifies

**(A) `scripts/scan_many.py` -- `scan_many(bt, sym, tf, method, overlays, workers=1)` == `[bt.scan(sym, tf, only=(method,), opts=o)
for o in overlays]`, byte for byte.** Overlays that agree on the keys that reach the expensive half share it:

* ICT: an *analysis group* = overlays agreeing on `ict-scan.ANALYZE_OPT_KEYS = (fx_b1_pivot1, fx_b2b_ce_fail, fx_b_pool)` (and on
  the bias-reading `methods`). The registry sits next to `V_ICT`; `test_speed_equivalence.AnalyzeKeyRegistry` derives the true
  set from `analyze()`'s own source (`ast`: every `opts.get("k")` / `opts["k"]`, and that `opts` is not handed on) and, separately,
  by perturbing **every** `fx_` key of the engine against ~100 real windows -- the tuple must equal exactly the keys whose value
  changes `analyze()`'s output. A key added to `analyze()` without being listed fails that test. Per bar the analysis is
  computed once and each overlay runs its own downstream half.
* WYCKOFF-BOOK: a *detection group* = overlays agreeing on the window length and `bt._wy_detection_ck()` (the two registries
  `_FX_WYCKOFF_DETECTION_KEYS` + `_FX_WYCKOFF_V_DETECTION_KEYS` that already existed); `WyckoffDetectionKeyRegistry` checks the
  source reads only registered keys and that perturbing every OPTS key changes detection only for registered ones.
* To share the code rather than duplicate it, the per-bar / per-fire bodies of `ict_setups_live()` and `scan()` were moved
  **verbatim** into `_ict_ctx`, `_ict_candidate` (before the `seen` check), `_ict_trade` (after it), `_wy_window`, `_wy_fire`;
  `ict_setups_live()` and `scan()` call them, so there is one implementation.
* Nothing is cached across bars (450,000 analyses would not fit): the overlays of a group advance bar by bar in lockstep,
  so memory does not grow with the number of value sets.
* Fallback: any method other than ICT / WYCKOFF-BOOK (COMBINED-BOOK) is a plain loop of `bt.scan()`. Every overlay is validated
  (`_check_fx_registered`, V-set checks, the W6 window check) before any work, raising `bt.scan`'s own error.

`fund-search.py`: `BtEngine.prefetch(values_list)` fills a raw-scan cache with one `scan_many` per symbol; `trades_for` is
unchanged apart from reading that cache and memoising its result. `evaluate_with_engine` first runs `prefetch_waves`:
**wave 1** = baseline + every single-factor candidate, **wave 2** = the per-fold combined chosen sets and every perturbation
set. Both lists are *discovered* by running the real `nested_walk_forward` / `perturbation_trade_sets` against a probe
(`_WaveProbe`: answers held sets for real, records the rest and answers them with no trades -- which cannot change what a stage
selects), not restated. `CountingSource` is untouched and still counts a set when the evaluation first scores it, so N and its
first-use order are unchanged (tested). A request the probes missed is still served by a plain scan: a wrong probe costs time,
never a result.

**(B) Constant-factor wins, each one byte-identical and tested against BASE's own code:**

| change | why byte-identical |
|---|---|
| `wyckoff_rules.swings()` / new `pivot_index()`: early-exit comparison loops instead of two `all()` generators per bar | same predicates (`H[j] <= H[i]`, NaN compares False in both); random tie-heavy series and real windows vs BASE |
| `swings(pivots=)`, `window_pivots()`, `detect_accumulations/distributions(pivots=)`, `_wyckoff_candidates(pivots=)`: pivots computed **once per series** and sliced per window | a k-bar pivot at bar i reads only i-k..i+k, all inside the window for every bar the window loop visits, so its flag is window-independent; the mirror side swaps the high/low flags (proved by the random and real-window tests, both sides) |
| `detect_accumulations`: only the last `max(nd+1, 2)` low / high swings are collected (walk back from the candidate) instead of two full comprehensions | only those elements are ever read (`lows[-j]`, `highs[-j]`, `lows[-2]`) |
| `detect_accumulations`: `spread` built lazily (`_LazySpread`) | it feeds two gates most windows never reach |
| `ict-scan.analyze`: early-exit pivot tests; FVG mitigation scan branches on type once; sweep scan branches on kind once; pool dedupe via a per-kind sorted level list + the *original* `abs(...) <= tol` test on the few candidates in a 1e-9-widened reach; swing price lists indexed once; day table without a per-bar dict | same values and same order of every comparison; `analyze()` output compared with `==` **and** `repr` to BASE's on ~340 real windows (US500 5m, XAUUSD 15m, US30 1m, XAGUSD 30m) x 5 opts variants x 3 method sets, plus tie-heavy synthetic windows down to 3 bars; `setup_candidate` likewise under 5 more option sets |
| `ict-scan.setup_candidate`: the O/H/L/C/T column lists are built after the two early `return None` exits | pure reorder; also asserts `setup_candidate` does not mutate the analysis it is handed (which is what makes sharing one analysis between overlays safe) |
| `scan()`: `all_pivots` (feeds only COMBINED-BOOK's `find_ict`) computed only when COMBINED-BOOK is wanted | pure function of the series, output unused otherwise |

**(C) Parallelism.** `scan_many(workers=W)` cuts each group's bar range into chunks and runs them in
`isolated_pool.IsolatedExecutor` (one spawned process per task; a crashed process fails only its own task, retried up to 2
times). Both engines dedupe a setup on its first bar (`seen`); everything after that check is a pure function of (bar, setup).
A chunk therefore records the first occurrence of each key **inside it, with its computed result (None included)**, and the
merge replays the records in bar order keeping the first occurrence of each key -- exactly the sequential loop. Results are
merged in (group, chunk) order, never completion order, so the worker count cannot change an output (tested: `workers=1` and
`workers=4` give identical outputs, and both equal BASE's). `fund-search --workers` (default `min(cpu-2, 10)`) is now the
process budget of that pool; candidates run one at a time, so the budget is never multiplied. `clamp_workers` lowers it so
the workers and the parent fit in 60 % of RAM (Section 6).

**Deliberately not done.** (1) Series-level precompute for `ict-scan.analyze()` (pivots and FVG first-mitigation could be
sliced per window the way Wyckoff's pivots are; ~35 % of analyze) -- it needs a new parameter through `read_at` /
`structures.ict_analysis` / `analyze`, and after (A) analysis is only (2 groups x 2 waves) = 4 passes per symbol; it is the next lever
if a smaller ICT wall time is needed. (2) Wiring `scan_cache.py`'s disk cache into `scan_many` -- not needed for a cell that runs
once, and a second key recipe would be a second thing to keep correct. (3) Anything in `walk`, `simulate`, `fund_stats`.

## 3. Equivalence evidence (`scripts/tests/test_speed_equivalence.py`)

The reference is BASE's own code (`git archive fef6d6b` extracted to a temp tree and run in a child process; `load_git_revision`-style
module loads for the unit-level checks), never a restated expectation. Real data = FTMO slices written to a temp history
root selected with `BT_HISTORY_ROOT`.

* `IctDifferential` (US500 5m, 7,000 bars, 18 overlays) and `WyckoffDifferential` (XAUUSD 15m, 30,000 bars, 16 overlays): `scan_many`
  == N independent BASE `bt.scan` calls, compared as `==` and as `repr` (types, key order, float text). The overlays cover every V
  key, the F keys, both analysis groups (`fx_b_pool`, `fx_b1_pivot1`, `fx_b2b_ce_fail`), `htf`, B3 (`tfa_p5`), B7, `mgmt`, `sides`, the
  W4a/W6/W-TW detection groups and W7. Also: forced 3- and 7-chunk decompositions; **`workers=1` vs `workers=4` identical and equal
  to BASE**; overlay order irrelevant; the reference is asserted non-vacuous (> 10 trades, > 3 distinct outputs).
* `AnalyzeAndSetupCandidateEqualBase`, `PivotPrecomputeEqualsBase`: unit-level equality with BASE (previous section).
* `BtEngineParity`: the real `BtEngine` -- `prefetch` then `trades_for` equals `trades_for` alone (trades, admission rows,
  rollover-edge rows), in-process and with a 3-process pool, ICT and Wyckoff.
* `FundSearchWaves`: the waves request exactly what the evaluation later asks for (no on-demand scan), the result and
  `runs_evaluated` are unchanged, wave 1 == baseline + every single-factor candidate, the probe never counts or scores.
* Full-scale spot checks (sha256 of the trade lists, `json.dumps(..., sort_keys=True)`): ICT XAUUSD 15m full development span
  (453,893 bars, 139 trades) BASE `0fbc43e33541e172` == NEW chunked with 10 workers `0fbc43e33541e172`; WYCKOFF-BOOK same series
  (416 trades) BASE `c25c253a624c87c7` == NEW `c25c253a624c87c7`; ICT US500 5m full span (177,185 bars, 113 trades) BASE
  `7799a8ca6c696676` == NEW `7799a8ca6c696676`. Every 2-year benchmark below compared its per-overlay digests with BASE's too.
* v1 proof: `PYTHONPATH=. python3 -W ignore scripts/stability-report.py --tf 4H --symbols AUS200 --workers 1 --out ... --json ...`
  on this tree and on a detached worktree of fef6d6b: `.md` byte-identical (`cmp`), `rows` equal (9 rows); the only JSON key that
  differs is `dataset_snapshot` (its `code_version` stamps the dirty tree vs the clean SHA). `/tmp/speed-v1-proof.log`.

## 4. Benchmarks (Step 3)

Workloads: US500 5m (140,309 bars) and XAUUSD 15m (47,361 bars), both cut to the fixed window 2022-03-01 .. 2024-03-01; N = 8 V
overlays, each plus the fund-search fixed keys (flat-before-rollover, FTMO rollover provider).
ICT: baseline, `fx_b_ex=ce`, `fx_b_pd=r13`, `fx_b_pool=on`, `fx_b_buf=0.1atr`, `fx_b_exit=-2.25|1.5H|floor`, `fx_b_lb=8|K`, `fx_b6=yes`.
Wyckoff: baseline, `fx_w_stop=spring_low`, `fx_w4a_linger_closes=2`, `fx_w6_window=600`, `fx_w_spt=ceiling`, `fx_w_touch=on`,
`fx_w_tw=(8,2)`, `fx_w_spt=VAH`. BASE = 8 independent `bt.scan` calls on fef6d6b (Wyckoff therefore *with* its in-process detection
cache). Serial columns were measured six processes at a time (same load for BASE and NEW); the 10-worker rows alone.

| workload | bars | BASE, 8 scans | NEW `workers=1` | speedup | NEW `workers=10` | speedup | trades per overlay (both engines) |
|---|---|---|---|---|---|---|---|
| ICT US500 5m | 140,309 | 1414.6 s | 256.7 s | **5.5x** | 35.6 s | **39.7x** | 83,152,108,83,83,83,60,78 |
| ICT XAUUSD 15m | 47,361 | 486.9 s | 86.8 s | **5.6x** | 12.4 s | **39.3x** | 11,20,12,11,11,11,8,11 |
| WYCKOFF-BOOK US500 5m | 140,309 | 352.7 s | 103.0 s | **3.4x** | 18.2 s | **19.4x** | 157,157,158,168,158,125,157,158 |
| WYCKOFF-BOOK XAUUSD 15m | 47,361 | 117.9 s | 32.2 s | **3.7x** | 5.8 s | **20.3x** | 59,59,59,61,59,50,59,59 |

One value set (N = 1), i.e. what the constant-factor work (B) and the chunk pool give without any sharing:

| workload | BASE | NEW `bt.scan` (B only) | NEW `scan_many` 10 workers |
|---|---|---|---|
| ICT US500 5m, 140,309 bars | 175.3 s | 106.8 s (1.64x) | -- |
| ICT XAUUSD 15m, 47,361 bars | ~60.9 s (486.9 / 8) | -- | 7.4 s (~8x) |
| WYCKOFF XAUUSD 15m, 47,361 bars | 21.3 s | 12.3 s (1.73x) | 1.7 s (12.5x) |

Full development span, XAUUSD 15m (453,893 bars), 10 workers, byte-identical to BASE (digests above):

| run | BASE | NEW |
|---|---|---|
| ICT, 1 value set | 664 s measured while a 10-process job ran (581 s quiet, per the brief) | 68.1 s |
| ICT, **26 value sets** (2 analysis groups) | 26 x 581 s = 15,106 s (4.2 h), extrapolated | **142.8 s (106x)** |
| WYCKOFF, 1 value set | 202 s (sampler run, quiet machine) | 19.4 s (10x) |
| WYCKOFF, 8 value sets (4 detection groups) | -- (not run; 2-year row above) | 61.0 s |

## 5. After the change -- where the time goes now

ICT US500 5m, full span, one value set through `scan_many` (132.8 s under the sampler vs 219.3 s BASE): `analyze` 95.5 % (`add` 11.3 %,
`leg_disp` 6.7 %); `_ict_candidate` 1.0 %, `_ict_trade` 0.8 %. **The per-value-set tail is ~2.3 microseconds per bar per set** (measured: 1, 9 and 20
value sets in the same group cost 23.4 s, 24.5 s, 26.0 s on 58,442 1m bars), so after (A) a value set that shares an analysis is nearly free
and the cost is `analysis groups x passes`.
WYCKOFF XAUUSD 15m, full span, one detection group (58.2 s under the sampler vs 202.1 s BASE): `_wyckoff_candidates` 78 %
(`detect_accumulations` 64 %, of which `swings` 12 %, the mirror `inv` lambda 11 %, `window_pivots` 10 %).

## 6. Memory per worker

A worker loads the full (symbol, timeframe) series -- forward walks need every later bar -- so it is `base + per-bar x bars`. Measured
on the real development series (peak RSS of one `_worker` after `bt.load`, `memprobe`): XAUUSD 15m 453,893 bars **346 MiB**;
5m 1,316,783 bars **971 MiB**; 1m 4,096,182 bars **3,045 MiB** (~741 B/bar; the Wyckoff kernel, pivot index included, measured 2,832 MiB on the same 1m series -- the ICT kernel also carries the id-of-time index). A real chunk run
(full 15m, `scan_many`, 10 workers) peaked at 391 MiB per child. `scan_many.WORKER_BASE_BYTES / WORKER_BYTES_PER_BAR` = 128 MiB /
850 B (the measurements rounded up ~15 %); a test pins the estimate >= every measurement. `clamp_workers` keeps
`(workers + 1 parent) x estimate <= 60 %` of physical RAM: on this 38.65 GB Mac the metals-1m cell (4.1 M bars per symbol,
estimate 3.6 GB) runs with **5** workers, not 10; the 1.0-1.7 M-bar cells with 10. Unknown RAM (no `sysconf`) means no clamp. The clamp
changes wall time only, never a result.

BASE's Wyckoff path also keeps one `_WY_CANDIDATES` entry per detection group *alive for the whole process* (~1 GB per group at
4 M windows x 2 sides); `scan_many` holds none.

## 7. Projected wall time

Model (measured inputs, serial, this Mac): BASE ICT 0.64 / 1.24 / 1.28 / 1.10 ms per bar per value set (1m / 5m / 15m / 30m); NEW ICT analysis
0.35 / 0.77 / 0.77 / 0.65 ms per bar for the pool-off group and x1.36 for the `fx_b_pool=on` group, tail 2.3 us per bar per set; BASE
Wyckoff 0.44-0.45 ms per bar per detection group; NEW Wyckoff 0.13 ms per bar per detection group. Wave sizes come from running
the real `prefetch_waves` on the real grids with a zero-edge synthetic engine (an upper-typical case: every fold picks something):
ICT wave 1 = 39 sets, wave 2 = 148 sets (17 folds; 100 with 10 folds, 43 with 4), always 2 analysis groups, and **wave 2 repeats both analyses**;
Wyckoff wave 1 = 14 sets in 9 detection groups, wave 2 = 29-93 sets in 11-26 groups (5-11 of them `fx_w6_window=600`, ~2x a group) =
~34 group-equivalents in total. Parallel efficiency 0.8: measured 0.56-0.72 on the runs above (10 workers, 47 k-453 k bars; per-worker load and spawn are a large share
there and shrink with task size), so the wall column is a central value and the range quoted for the heaviest cell spans 0.6-0.9. Baseline "41 sets" is the brief's basis (N), "187" the wave sizes above.

| tf | cell | bars | workers | ICT BASE (41 / 187 sets) | ICT NEW CPU / wall | WYCKOFF BASE | WYCKOFF NEW CPU / wall |
|---|---|---|---|---|---|---|---|
| **1m** | **metals** | **8,194,086** | **5** | **59.7 h / 272 h** | **4.7 h / 1.2 h** | **34 h** | **10.1 h / 2.5 h** |
| 1m | indices | 4,998,552 | 10 | 36 h / 166 h | 2.9 h / 0.36 h | 21 h | 6.1 h / 0.8 h |
| 5m | metals | 2,370,864 | 10 | 34 h / 153 h | 2.7 h / 0.33 h | 10 h | 2.9 h / 0.36 h |
| 5m | indices | 1,030,696 | 10 | 15 h / 66 h | 1.2 h / 0.15 h | 4.4 h | 1.3 h / 0.16 h |
| 15m | metals | 811,587 | 10 | 11.8 h / 54 h | 0.9 h / 0.11 h | 3.4 h | 1.0 h / 0.12 h |
| 15m | indices | 359,449 | 10 | 5.2 h / 24 h | 0.4 h / 0.05 h | 1.5 h | 0.44 h / 0.06 h |
| 30m | metals | 410,388 | 10 | 5.1 h / 23 h | 0.4 h / 0.05 h | 1.7 h | 0.5 h / 0.06 h |
| 30m | indices | 188,942 | 10 | 2.4 h / 11 h | 0.18 h / 0.02 h | 0.8 h | 0.23 h / 0.03 h |

(The BASE 15m-metals ICT figure, 11.8 h, matches the brief's ~13 h.) **Heaviest cell = metals 1m**: ICT ~1.2 h (1.05-1.6 h for efficiency
0.9-0.6) and Wyckoff ~2.5 h (2.2-3.4 h) wall on this Mac with 5 workers, ~3.7 h for both, against ~94 h (~4 days) serially at BASE on the
brief's 41-set basis (~12.8 days on the 187-set wave sizes). Every other cell is under an hour per method. These are projections from
measured per-bar costs, not measured full cells; the full-span XAUUSD 15m runs above are the largest direct measurement.

## 8. Operating notes and open items

* `scripts/fund-search.py` `FINGERPRINT_FILES` now also lists `scripts/scan_many.py` and `scripts/structures.py`; because the engine files
  changed, `fund-search declare` must be re-run for the new code before `run` (drift refusal is by design).
* `fund-search run --workers N`: N is now the scan-pool budget inside each candidate (candidates run sequentially); default
  `min(cpu-2, 10)`; CI's `--workers 2` is honoured (the memory clamp will usually drop a 7 GB runner to in-process on 1m series).
* Test files touched because engine function boundaries moved (no assertion weakened): `test_live_rules` (the two "ict_setups_live uses
  setup_candidate / fvg_fill" source checks now read `_ict_candidate` / `_ict_trade` too) and `test_snapshot_options_have_readers`
  (`_READER_FUNCTIONS` lists the moved bodies, as its own docstring instructs).
* Pre-existing failures, identical on fef6d6b and on this branch (same failing test names): `test_doc_citations` (2),
  `test_instruments_sync` (1), `test_quality` (1 error), `test_trading_system` (2), `test_strategy_runner` (17 failures, 2 errors).
* Next levers if wall time matters: series-level pivots/FVG-mitigation for `analyze()` (Section 2, "not done"); a wave-1 tail-only
  pass cannot avoid wave 2's second analysis because wave 2 depends on wave 1's selection; raising `MEMORY_FRACTION` (or a CLI flag) for the
  metals-1m cell if the machine has spare RAM.
