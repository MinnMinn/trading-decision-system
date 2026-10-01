# Fund search on GitHub Actions: scan-cache sharding (2026-09-30)

Branch `b5-actions-shard`, from `windows-migration` 4d9bb8e. Scope: let the heavy fund-search cells (1m metals, 1m indices, and
in practice every cell above ~30m) run across GitHub Actions jobs, **without changing any statistic, threshold, grid, OPTS key,
the plan (`plan_hash b3f295ddfb1757ea`, unchanged) or the declaration's pinned settings.** Nothing was pushed, no workflow was
triggered, `declare` was not run, no real-history scan beyond a 7,000-bar test slice was run.

## 1. Problem, with the numbers that were given

`.github/workflows/fund-search.yml` (before) ran one job per cell (`run --cell C`, both methods, `timeout-minutes: 350`; GitHub's
cap is 360). Owner measurement on 10 local M-series workers: ICT XAUUSD 1m wave 1 (39 value sets) took ~2.4 h = **581 s for the
first value set + ~213 s per further set**. The expensive part is `BtEngine.prefetch` (`scan_many`, bar-chunk parallel), whose
per-(value set, symbol) output is cached in `BtEngine._raw`/`_done` (`scripts/fund-search.py`). The statistics (nested
walk-forward, pooling across symbols, stability, prop pass) are cheap by comparison and stay in ONE step per cell.

## 2. Design

```
plan ──> scan_wave1 (matrix: cell x method x symbol x slice) ──> scan_wave2 (same axes) ──> evaluate (per cell) ──> report
         raw scans of the wave-1 value sets,          wave-2 sets, chosen from the POOLED     run --scan-cache: pooling,
         ONE symbol, uploaded as artifact             wave-1 trades of every symbol of the    walk-forward, stability, every
         fund-scan-<cell>-<method>-<symbol>-w1-s<i>   cell (needs that cell's complete        verdict, in ONE step, unchanged
                                                      wave 1); ONE symbol per shard
```

* `fund-search.py scan --cell C --symbol S --method M --out DIR [--workers N] [--wave 1|2] [--slice I/N] [--scan-cache DIR ...]`
  builds the `BtEngine` for one symbol (wave 1) or the whole cell (wave 2: selection needs every symbol's trades) and asks the
  **real** `nested_walk_forward` / `perturbation_trade_sets` (through the existing `_WaveProbe`, now exposed as `wave1_values` /
  `wave2_values`, which `prefetch_waves` itself calls) which value sets each wave needs, so the lists cannot drift from what `run`
  later requests. It scans only its symbol (`BtEngine.scan_symbol`, one `scan_many`) and writes one cache entry per (value set, symbol)
  the moment the scan returns. Like `run` it refuses without the ledger declaration and on code drift, and refuses an `--out`
  inside the checkout (CLAUDE.md section 46).
* `run --scan-cache DIR` (repeatable): `BtEngine.load_scan_cache` verifies every entry, puts a value set whose symbols are all cached
  into `_raw[key]` (byte-for-byte what `prefetch` would have produced), keeps a partly cached set in `_part` and scans **only the
  missing symbols** (`prefetch` / `trades_for`); everything else is scanned on demand as before. `trades_for` (timeout exclusion, the
  admission and rollover-edge rows, `checked_simulate`, adx14) is untouched and runs on the cached raw lists in the evaluating job.
* Without `--scan-cache` the code path is unchanged: `_evaluate_candidate` keeps its 3-argument call shape (tested).

### What is and is not symbol-local

| piece | symbol-local? | where it runs |
|---|---|---|
| raw `scan_many` output for (value set, symbol) | yes | shard |
| wave-1 value-set list (baseline + every single-factor candidate) | yes (needs no trades at all) | shard |
| wave-2 value-set list (each fold's combined chosen set, every perturbation set) | **no**: chosen by `select_values` on the *pooled* training trades of all symbols | any job that holds the cell's complete wave 1 (`scan --wave 2`, or `run`) |
| raw scan of a given wave-2 value set for one symbol | yes, once the list is known | wave-2 shard |
| `trades_for` post-processing, `checked_simulate`, admission / rollover-edge rows, adx14 | **no**: `simulate` pools all symbols, so its `taken` set depends on the other symbols | evaluate job |
| walk-forward, stability, per-symbol pooling, prop pass, verdicts | no (by design: "ONE evaluate step per cell") | evaluate job |

**Deviation from the brief, deliberately:** the brief suggested persisting "trades incl. adx14 and the admission/rollover rows". Those
are outputs of `trades_for`, i.e. of `simulate` over the *pooled* raw trades of all symbols; a per-symbol copy would either be wrong
or reimplement simulate's pooling. The cache therefore holds the **raw pre-simulate scan lists** (the expensive, symbol-local part) and
the evaluating job recomputes adx14/admission/rollover rows itself. A test proves trades, `_admission`, `_edge` and every record
value are identical to a cache-less run.

Wave 2 therefore cannot be sharded *before* wave 1 exists. It is not "changing statistics" to shard it after: the pipeline above is
two symbol-local scan phases separated by one cheap pooled step (selection, done by the wave-2 job that needs it).

### Cache key, identity and refusal

Entry file `<sha256>.json`, deterministic bytes (no timestamp, atomic write, `*.tmp` never read). `key = sha256(canonical JSON of
{stamp, scope})`:

* `stamp` (must equal THIS run's for **every** `*.json` under the cache dirs, whatever cell it is for): `format`, `plan_hash`,
  `code_fingerprint()` (last-commit SHA + dirty flag of each `FINGERPRINT_FILES` entry) **plus the sha256 of each of those files' content**
  (two dirty trees never look alike), and `evaluation_config(plan)` (everything `declare` pins: stability fractions, block days,
  embargo, adopted F keys, grid sha256, ...).
* `scope`: `cell`, `runner_method`, `timeframe`, `symbol`, `value_key`, and `series` = bar count, first and last bar **and a sha256 of the
  whole PIT-truncated candle series** the scan read (streamed in 50,000-bar chunks; computed once per engine). A history file that changed
  in the middle of the series, with the same length and end bars, is therefore refused too. Cost: one pass over each series when an
  engine is built (seconds to a few tens of seconds at 4 M bars; not measured here).

`run` / `scan --wave 2` REFUSE (`ScanCacheRefused`, exit non-zero, nothing evaluated) on: a stamp difference (message names the
differing field, e.g. `code.scripts/fund-search.py` or `plan_hash`); a `series` that differs from what the engine itself loaded; a
file that is torn / not JSON / structurally incomplete; a file whose name or recorded key does not match its content hash (renamed,
edited, foreign); a `trades_sha256` or `n_trades` mismatch (edited or corrupted); two entries for the same (value set, symbol) that disagree;
a missing cache directory; and, for `--wave 2`, an **incomplete wave 1** (the wave-2 sets would be chosen from a partial pool).
Completeness is judged against the wave-1 **key list** (the list a holding-nothing engine derives), not by re-running the selection: with real
trades held, a fold's combined set (>= 2 changed factors) is legitimately not a wave-1 set (fix round 1, C1; tested with a selection that only
becomes visible once trades are held, `ScanCacheHeldSelection`). Only wave-1 keys are loaded by `--wave 2`, so the wave-2 list, and therefore
each shard's slice, never depends on which wave-2 entries a directory happens to hold.

**What the hashes are and are not.** `trades_sha256` and the content-hash file name detect corruption, torn copies, casual edits and
mix-ups. They are self-consistency checks, **not authentication**: anyone who can rewrite a file can rewrite its hashes. A cache directory is
therefore trusted only as far as its provenance (artifacts of the same workflow run, same commit). The `series.sha256` and the stamp bind an
entry to the data and code it claims, again as consistency, not as a signature.

**Run-time guard and provenance.** `run --scan-cache DIR --require-complete-scan-cache` sets `engine.no_scan`: any `scan_many` / `bt.scan` that
would have to run on demand raises `ScanCacheRefused` (the workflow's evaluate job uses it, so a cell can never fall back to a multi-hour
scan). The sealed record's `parameters.scan_cache` = `{entries, complete_value_sets, sha256_of_sorted_entry_keys}` is stamped **only when
`--scan-cache` is used**; it sits beside `plan_hash` in `parameters`, is read by no statistic, `validate_record` or the report, and does not touch
`plan_hash` or any hashed/pinned field. A cache-less record is unchanged, so a cache record differs from a cache-less one in exactly that key
(the evaluation result, `metrics`, is identical -- tested).
Entries of another cell/method/timeframe made by the *same* code are ignored, not used. `write_scan_entry` refuses to write trades that
do not survive a JSON round trip unchanged (type, key order, float text), so a cache can never alter a trade.

## 3. Time estimates

**Calibration status: read this first.** Every number below rests on ONE measured run: ICT, XAUUSD 1m, wave 1, 39 sets, 10 workers, ~2.4 h,
from which the model takes 581 s for the first set and ~213 s per further set. **That first-set figure (581 s) is exactly the figure the earlier
engine-speed audit reports for XAUUSD 15m** (docs/audits/2026-09-30-engine-speed-profile.md section 4: "581 s quiet, per the brief"), a series with ~9x
fewer bars (453,893 vs 4,096,182). That coincidence is suspicious: the 581 s may be a 15m number carried over rather than a 1m measurement, in which case the
first-set cost on 1m is understated. Two further calibration runs (Wyckoff XAUUSD 1m, ICT US500 5m) are in progress; **the model must be recalibrated when they
land and `list-scan-shards` re-run** (the slice counts, and so the matrix, will change; results will not). Until then treat every minute figure as an order of magnitude.

**Model** (`SHARD_MODEL`, `shard_seconds` in `scripts/fund-search.py`; `list-scan-shards --explain` prints the full table):

* Taken from that single run (given, not independently verified): 581 s first set, ~213 s each further set, ICT XAUUSD 1m, 39 sets, 10 workers (= 8,675 s = 2.41 h).
* **Not modelled, per-shard fixed costs:** every shard pays checkout, Python setup and `BtEngine` construction, which loads and indexes the candle series
  (adx index, `series.sha256`) of every symbol the shard's engine holds -- ONE symbol for wave 1 but **all the cell's symbols for wave 2** (5 indices, or 2 x ~4 M bars
  for 1m metals). A wave-2 shard also verifies the cell's whole wave-1 cache (every entry is read and hashed) and runs `trades_for` on every wave-1 set
  (`wave2_values` needs their pooled trades) before it scans anything. None of this is measured; it is paid once per shard, so it matters most for the many
  small slices (1m metals: 17 to 36 wave-2 slices per symbol).
* **Memory risk, wave 2 on 1m metals:** the shard's process holds both ~4.1 M-bar series (2 x ~3.4 GiB at the audit's ~779-850 B/bar) plus the scan's own arrays and the wave-1
  trade lists, inside 16 GiB (and inside 7 GiB if the runner is the private-repo 2 vCPU / 7 GB one, where it would not fit). Fits on paper for 16 GiB, unmeasured; an OOM
  kills the job. `scan_many.clamp_workers` sizes only the scan workers, not the parent's second series.
* Assumed, not measured: cost linear in bars (reference 4,096,182); linear in workers (reference 10); runner = 4 vCPU / 16 GiB with
  `scan_many.clamp_workers` (60 % of RAM: `worker_memory_estimate(4,096,182)` = 3.37 GiB per worker, so **the 1m metals series run with 1
  worker**, US30 1m and the 5m/15m/30m series with 4); no per-core speed adjustment for a hosted runner; Wyckoff = 2.0 x ICT per set
  (the engine-speed audit projects ~2.1x on 1m metals; not measured here); wave-2 size = 11 (ICT) / 8 (Wyckoff) sets per fold, an
  upper-typical bound from the audit's zero-edge wave runs (ICT 148 @17 folds, 100 @10, 43 @4; Wyckoff 29-93 @ 4-17 folds), because the
  real wave-2 size depends on the selection. Bar counts are the audit's development-span table (docs/audits/2026-09-30-engine-speed-profile.md, header).
* **Discrepancy to flag:** the engine-speed audit (section 5/7) models the per-extra-value-set cost at ~2.3 microseconds/bar (~10 s on
  4.1 M bars) and projects the 1m-metals ICT cell at ~1.2 h wall on 5 workers, while the owner's measurement is ~213 s per extra set.
  I use the measurement; I do not know why they differ (candidate causes: more analysis groups than the audit assumed, the machine
  being busy, or the run being the clamped 5 workers). If the measurement was really at 5 effective workers rather than 10, every 1m-metals number
  below is ~2x too pessimistic; if the runner core is slower than an M-series core, they are optimistic.
* If the repository is private, `ubuntu-latest` is a 2 vCPU / 7 GB runner, not 4 vCPU / 16 GB: everything above roughly doubles and the memory clamp
  drops more series to in-process. I could not check the repository's visibility. **Hosted-runner concurrency limits were not verified** either.

**Which pieces exceed 355 min if NOT split** (model; one job, the same symbol/wave, no slicing):

| piece | modelled | note |
|---|---|---|
| 1m-metals ICT wave 1, one symbol (39 sets) | 1,446 min (24 h) | XAUUSD and XAGUSD |
| 1m-metals Wyckoff wave 1, one symbol (14 sets) | 1,117 min (19 h) | |
| 1m-metals wave 2, one symbol | ICT 3,576 min (99 sets), Wyckoff 5,236 min (72 sets) | |
| every other wave-1 symbol shard | 2-153 min (1m US30 ICT the longest) | fits |
| 1m-indices wave 2, one symbol | ICT 171 min max (US30), Wyckoff 253 min max (US30) | fits per symbol |
| 5m-metals wave 2, one symbol | ICT 538 / 431 min, Wyckoff 786 / 629 min | exceeds |
| 15m-metals / 30m-metals wave 2, one symbol | 74-271 min | fits |
| **wave 2 inside the evaluate job** (all symbols pooled, one job, the brief's wave-1-shard + wave-2-in-evaluate layout) | 1m-metals 17,625 min, 1m-indices 1,226, 5m-metals 2,384, 15m-metals 816, 30m-metals 413 (both methods); 5m-indices 253, 30m-indices 46, 15m-indices 88 fit | **so wave 2 must be sharded too**; the wave-1-only design is not enough for 5 of 8 cells |

**Further split, implemented (small):** `--slice I/N` takes the I-th of N contiguous parts of a wave's value-set list (contiguous so
value sets that share an analysis group stay together; every set is independent, so slicing cannot change a value). `list-scan-shards`
picks N per (cell, method, symbol, wave) so the modelled shard is <= 300 min (`budget_s`; the job timeout is 355, GitHub's cap 360).
Resulting layout (`list-scan-shards --explain`, 244 shards: 80 wave 1 + 164 wave 2):

| cell | ICT wave 1 slices/symbol (sets) | ICT wave 2 slices/symbol | Wyckoff wave 2 slices/symbol | longest shard |
|---|---|---|---|---|
| 1m-metals | 7 (39) | 17 (99) | 36 (72) | 274 min |
| 1m-indices | 1 | 1 | 1 | 253 min (Wyckoff wave 2, US30) |
| 5m-metals | 1 | 2 (187) | 3 (136) | 273 min |
| 15m-metals | 1 | 1 | 1 | 271 min (Wyckoff wave 2) |
| 5m/15m/30m-indices, 30m-metals | 1 | 1 | 1 | <= 137 min |

No shard is modelled over 355 min. **The irreducible unit is one value set of one symbol** (5,810 s = 97 min at 1 worker on 1m metals
in this model; 194 min for Wyckoff); splitting below that would need a bar-chunk-range split, which is NOT implemented (it would change how
`scan_many` merges and needs its own equivalence proof) -- not required in this model; it would be if the real first-set cost on 1m metals is above ~3x the model (ICT) or ~1.5x (Wyckoff).

**Cost, honestly:** modelled total ~**706 runner-hours** (42,383 shard-minutes, 244 jobs), of which 1m-metals is ~592 (ICT ~212, Wyckoff ~380), before the per-shard
fixed costs above and under the calibration caveat. Wall time depends on how many of the 244 jobs the account may run at once; **hosted-runner concurrency limits were
not verified**, so no wall-clock figure is offered here (the longest single shard is modelled at 274 min, and the pipeline has two such stages plus evaluate in series).
`scan_many` returns all the sets of one slice at once, so a shard killed at the timeout loses its own slice, not the others.
**Re-run behaviour:** "Re-run failed jobs" starts the failed shard on a fresh runner with an empty `--out`, so it **re-scans its whole slice**; the "present entries are
verified and skipped" logic in `scan` only helps when the same `--out` directory is reused (local resumption), not on a hosted re-run. Hence `overwrite: true` on the shard
uploads: the re-run's artifact replaces the failed attempt's (same name) instead of failing the upload.

**Evaluate job:** with a complete cache it does no scans; what remains is loading both symbols' series (1m metals ~2 x 3.4 GiB by the audit's
per-bar figure, fits 16 GiB but not measured here), adx indices, `trades_for` post-processing and `dataset_snapshot` hashing. Not measured; expected minutes,
not hours, but this is an estimate.

## 4. Workflow (`.github/workflows/fund-search.yml`)

`workflow_dispatch` only, `permissions: contents: read`, inputs and matrix values only via `env:` (validated in the script; the existing
`WorkflowHardening` test still passes), all outputs under `$RUNNER_TEMP` (outside the checkout, section 46), every job `timeout-minutes: 355`.
New jobs `scan_wave1` / `scan_wave2` upload `fund-scan-<cell>-<method>-<symbol>-w<wave>-s<slice>` (the requested
`fund-scan-<cell>-<method>-<symbol>` plus wave/slice suffixes, which are needed for uniqueness once a symbol has several slices).
`evaluate` downloads `fund-scan-<cell>-*` and runs `run --scan-cache --require-complete-scan-cache`. `plan` also emits `list-scan-shards --wave 1|2`, fails if
`docs/experiments/fund-search/plan.json` is not committed (`git ls-files --error-unmatch`), and has `timeout-minutes: 15` (report: 30). Each script step tails
the last 40 lines of its stderr log on failure, so a `ScanCacheRefused` reason shows in the job log. Both shard uploads set `overwrite: true`.

* **History root:** `main()` already does `os.environ.setdefault("BT_HISTORY_ROOT", data/history/ftmo)` before every command and `_load_bt`
  freezes it at exec, so `scan`, `run` and `plan` read the committed FTMO feed. The workflow also sets `BT_HISTORY_ROOT: ${{ github.workspace }}/data/history/ftmo`
  at workflow level, so no job can silently use another root. Costs come from the committed `data/history/costs/ftmo/`.
* **`fetch-depth: 0` added to every checkout that runs `plan`/`scan`/`run`.** `code_fingerprint()` is `git log -1 -- <file>` per pinned file; a depth-1
  clone (the default) contains one commit, so every file would report the same SHA and `run` would read as drift against a declaration made from full
  history. That is a defect of the pre-change workflow as well (I reasoned from git's shallow semantics; I did not run it in Actions).
* **Blast radius of `needs`.** `evaluate` has `needs: [plan, scan_wave2]`, and `needs` is per JOB, not per matrix entry: ONE failed or timed-out shard in ANY
  cell (e.g. a 1m-metals wave-1 slice) skips `scan_wave2` for every cell and therefore `evaluate` for every cell, including cells whose own artifacts are complete
  (the cheap 15m/30m cells wait behind, and are blocked by, the 1m metals shards). That is the fail-loud default and it is kept. Alternative: `if: ${{ !cancelled() }}` on
  `scan_wave2` and `evaluate` runs every cell whose artifacts happen to be complete; the others then fail fast at `scan --wave 2`'s incomplete-wave-1 refusal or at
  `--require-complete-scan-cache` (no multi-hour on-demand scan is possible either way), and the report lists the missing cells as NOT RUN. Trade-off: partial results
  arrive earlier, at the price of a run whose overall status is red-but-partial; choose it if the 1m cells are expected to be re-run separately.
* `docs/experiments/fund-search/plan.json` is not committed in this branch (`plan` writes it); it must be committed before triggering, as the
  pre-change workflow already required. In this worktree I ran `plan` only to test `list-scan-shards`, then deleted the file.

## 5. Determinism and research-integrity notes

* No hashed field moved: `plan_hash b3f295ddfb1757ea` and `plan --dry-run` output are byte-identical to 4d9bb8e (`/tmp/b5-plan-head.txt` vs `/tmp/b5-plan-new.txt`).
* **Pinned code changed:** `scripts/fund-search.py` (it is in `FINGERPRINT_FILES`). `scripts/fund_stats.py`, `scripts/scan_many.py` and the other pinned files are untouched.
  No declaration exists yet in `docs/architecture/research-ledger.json`, so nothing needs re-declaring; `declare` must simply be run from the final code.
* Slicing and sharding change only where a scan runs; a value set's raw trades are a function of (value set, symbol, code, data), which the entry identity
  pins; `CountingSource` still counts a set when the evaluation first scores it, so N and its first-use order are unchanged (asserted: `runs_evaluated` equal).
* Scanning is not evaluating, but it reads development history, so `scan` requires the same ledger declaration as `run`.

## 6. Tests

`scripts/tests/test_fund_search.py`: `ScanCache`, `ScanCacheHeldSelection` (C1 regression: a combined set that is not a wave-1 set; wave 2 accepted on a complete
wave 1, refused when one wave-1 set is absent; `--require-complete-scan-cache` fails loud), `ScanCacheTwoSymbols` (two symbols end to end, pooled run identical) -- all on the real `BtEngine` with
real ICT scans over 7,000-bar 5m slices, 4 real grid items. `ScanCache` covers:
cache run == no-cache run (result JSON, `runs_evaluated`, trades `repr`, admission and edge rows; on-demand scanning forbidden while it runs), non-vacuous wave 2,
deterministic bytes, rerun skips, partial cache, partly cached symbols, refusal on code / plan / settings / history (length and content) / edited file / dropped trade / torn / renamed /
missing directory / foreign entry, wave 2 refusing an incomplete wave 1, slice partition, `--out` inside the checkout, no declaration; `ShardLayout`; `ScanCacheRunPlumbing`.
The slice is far too short for selection to choose, so the tests wrap `select_values` (it still runs for real) to force "last candidate of every factor":
from the first probe on (`ScanCache`, which also makes the combined set a wave-1 set -- the shape that masked C1) or only once trades are held
(`ScanCacheHeldSelection`, `ScanCacheTwoSymbols`; wave 1 is then exactly baseline + candidates). A wholly unforced selection on a slice this small is not expected to choose
anything (not verified), so no test here exercises an unforced multi-factor choice; that path is covered by the held-trades stub and by the two-wave runs
of `test_speed_equivalence`.


## 8. Update 2026-10-01: six cells (the 30m cells were removed)

> **Pointer (added 2026-10-01, branch `b14-shard-calibration`): the time model below was CALIBRATED afterwards.** `docs/audits/2026-10-01-shard-calibration.md` replaces the 581 s / 213 s
> one-run model with rates fitted to real scans (detection-group cost, extra-set cost, per-shard fixed costs, measured wave-2 sizes, a runner-speed factor parameter), re-lays the matrix
> (124 shards for the declared three-cell plan, none over 300 modelled minutes at factor 2.0; 400.0 runner-hours at 2.0, 206.8 at 1.0) and corrects the "UNCALIBRATED" paragraph and the tables below, which are kept unchanged as the record of the old model.
> The 581 s first-set figure is confirmed there to be a 15m number (a full 15m XAUUSD ICT group is ~613 s in the calibrated model).

**Supersedes the layout figures of sections 3-4 for the CURRENT plan** (those sections describe the 8-cell plan and stay as the record of that state). The owner removed `30m-metals` and
`30m-indices` (2026-10-01; `docs/architecture/fund-search-cells.json`); the cell list is now a pinned, declared input of the plan (it changes `plan_hash`; it is pinned in the
declaration as `evaluation_config.cells_sha256`). The matrix below is `list-scan-shards` (the workflow reads it; nothing in `.github/workflows/fund-search.yml` names a cell) regenerated
for 6 cells, ICT N = 29 per cell (27 wave-1 sets after the baseline, `B-EXIT no_floor` removed 2026-09-30; sections 3-4 still show the older 39), Wyckoff 16 per cell.

**The time model is still UNCALIBRATED** (section 3, "Calibration status": one owner-measured run, the 581 s first-set figure suspected to be a 15m number, per-shard fixed costs not
modelled, runner speed assumed). Every minute figure below is the same model as before, applied to the new cell list; it must be recalibrated when the pending calibration runs land
and `list-scan-shards` re-run (slice counts, not results, will change). Per-cell history starts (`dev_start`) are all null today (every cell keeps its original data start), so the
bar counts are the audit's development-span table unchanged; a declared later start would scale a shard's modelled bars by the share of the span it keeps (`cell_bars`), an
estimate only.

Resulting layout: **212 shards (62 wave 1 + 150 wave 2), 40,485 modelled shard-minutes (~675 runner-hours; 1m-metals ~574 of them), longest shard 274 min, none over the 355-minute timeout**
(sections 3-4 state 244 shards / 42,383 minutes for the earlier 8-cell plan with the pre-`no_floor` set counts; the two changes were not separated here, so no attribution of the
difference is offered).

| cell | ICT wave 1 slices (sets) | ICT wave 2 slices | Wyckoff wave 1 slices | Wyckoff wave 2 slices | longest shard |
|---|---|---|---|---|---|
| 1m-metals | 5/symbol (27) | 17/symbol (99) | 7/symbol (14) | 36/symbol (72) | 274 min |
| 1m-indices | 1 | 1 | 1 | 1 | 253 min (Wyckoff wave 2, US30) |
| 5m-metals | 1 | 2/symbol (187) | 1 | 3/symbol (136) | 273 min |
| 5m-indices | 1 | 1 | 1 | 1 | 51 min |
| 15m-metals | 1 | 1 | 1 | 1 | 271 min (Wyckoff wave 2) |
| 15m-indices | 1 | 1 | 1 | 1 | 17 min |

Full `list-scan-shards --explain` output of the committed cell list (uncalibrated model; generated with `shard_plan(build_plan())`, the function `list-scan-shards` calls, before any
`plan.json` exists in this branch):

```
cell        method  symbol  wave slices  sets  unsliced  longest shard  shard over 355 min?
1m-metals   ict     XAUUSD  1         5    27   1020 min       274 min   no
1m-metals   ict     XAGUSD  1         5    27   1020 min       274 min   no
1m-metals   ict     XAUUSD  2        17    99   3576 min       274 min   no
1m-metals   ict     XAGUSD  2        17    99   3577 min       274 min   no
1m-metals   wyckoff XAUUSD  1         7    14   1117 min       265 min   no
1m-metals   wyckoff XAGUSD  1         7    14   1117 min       265 min   no
1m-metals   wyckoff XAUUSD  2        36    72   5235 min       265 min   no
1m-metals   wyckoff XAGUSD  2        36    72   5237 min       265 min   no
1m-indices  ict     US500   1         1    27     53 min        53 min   no
1m-indices  ict     US30    1         1    27    108 min       108 min   no
1m-indices  ict     USTEC   1         1    27     54 min        54 min   no
1m-indices  ict     DE40    1         1    27     47 min        47 min   no
1m-indices  ict     FRA40   1         1    27     50 min        50 min   no
1m-indices  ict     US500   2         1    44     84 min        84 min   no
1m-indices  ict     US30    2         1    44    171 min       171 min   no
1m-indices  ict     USTEC   2         1    44     86 min        86 min   no
1m-indices  ict     DE40    2         1    44     74 min        74 min   no
1m-indices  ict     FRA40   2         1    44     79 min        79 min   no
1m-indices  wyckoff US500   1         1    14     58 min        58 min   no
1m-indices  wyckoff US30    1         1    14    118 min       118 min   no
1m-indices  wyckoff USTEC   1         1    14     59 min        59 min   no
1m-indices  wyckoff DE40    1         1    14     51 min        51 min   no
1m-indices  wyckoff FRA40   1         1    14     55 min        55 min   no
1m-indices  wyckoff US500   2         1    32    125 min       125 min   no
1m-indices  wyckoff US30    2         1    32    253 min       253 min   no
1m-indices  wyckoff USTEC   2         1    32    127 min       127 min   no
1m-indices  wyckoff DE40    2         1    32    109 min       109 min   no
1m-indices  wyckoff FRA40   2         1    32    117 min       117 min   no
5m-metals   ict     XAUUSD  1         1    27     82 min        82 min   no
5m-metals   ict     XAGUSD  1         1    27     66 min        66 min   no
5m-metals   ict     XAUUSD  2         2   187    538 min       273 min   no
5m-metals   ict     XAGUSD  2         2   187    431 min       219 min   no
5m-metals   wyckoff XAUUSD  1         1    14     90 min        90 min   no
5m-metals   wyckoff XAGUSD  1         1    14     72 min        72 min   no
5m-metals   wyckoff XAUUSD  2         3   136    786 min       272 min   no
5m-metals   wyckoff XAGUSD  2         3   136    629 min       218 min   no
5m-indices  ict     US500   1         1    27     11 min        11 min   no
5m-indices  ict     US30    1         1    27     22 min        22 min   no
5m-indices  ict     USTEC   1         1    27     11 min        11 min   no
5m-indices  ict     DE40    1         1    27     10 min        10 min   no
5m-indices  ict     FRA40   1         1    27     11 min        11 min   no
5m-indices  ict     US500   2         1    44     18 min        18 min   no
5m-indices  ict     US30    2         1    44     34 min        34 min   no
5m-indices  ict     USTEC   2         1    44     18 min        18 min   no
5m-indices  ict     DE40    2         1    44     15 min        15 min   no
5m-indices  ict     FRA40   2         1    44     17 min        17 min   no
5m-indices  wyckoff US500   1         1    14     12 min        12 min   no
5m-indices  wyckoff US30    1         1    14     24 min        24 min   no
5m-indices  wyckoff USTEC   1         1    14     12 min        12 min   no
5m-indices  wyckoff DE40    1         1    14     11 min        11 min   no
5m-indices  wyckoff FRA40   1         1    14     12 min        12 min   no
5m-indices  wyckoff US500   2         1    32     26 min        26 min   no
5m-indices  wyckoff US30    2         1    32     51 min        51 min   no
5m-indices  wyckoff USTEC   2         1    32     26 min        26 min   no
5m-indices  wyckoff DE40    2         1    32     23 min        23 min   no
5m-indices  wyckoff FRA40   2         1    32     25 min        25 min   no
15m-metals  ict     XAUUSD  1         1    27     28 min        28 min   no
15m-metals  ict     XAGUSD  1         1    27     22 min        22 min   no
15m-metals  ict     XAUUSD  2         1   187    186 min       186 min   no
15m-metals  ict     XAGUSD  2         1   187    146 min       146 min   no
15m-metals  wyckoff XAUUSD  1         1    14     31 min        31 min   no
15m-metals  wyckoff XAGUSD  1         1    14     24 min        24 min   no
15m-metals  wyckoff XAUUSD  2         1   136    271 min       271 min   no
15m-metals  wyckoff XAGUSD  2         1   136    213 min       213 min   no
15m-indices ict     US500   1         1    27      4 min         4 min   no
15m-indices ict     US30    1         1    27      7 min         7 min   no
15m-indices ict     USTEC   1         1    27      4 min         4 min   no
15m-indices ict     DE40    1         1    27      3 min         3 min   no
15m-indices ict     FRA40   1         1    27      4 min         4 min   no
15m-indices ict     US500   2         1    44      6 min         6 min   no
15m-indices ict     US30    2         1    44     12 min        12 min   no
15m-indices ict     USTEC   2         1    44      6 min         6 min   no
15m-indices ict     DE40    2         1    44      5 min         5 min   no
15m-indices ict     FRA40   2         1    44      6 min         6 min   no
15m-indices wyckoff US500   1         1    14      4 min         4 min   no
15m-indices wyckoff US30    1         1    14      8 min         8 min   no
15m-indices wyckoff USTEC   1         1    14      4 min         4 min   no
15m-indices wyckoff DE40    1         1    14      4 min         4 min   no
15m-indices wyckoff FRA40   1         1    14      4 min         4 min   no
15m-indices wyckoff US500   2         1    32      9 min         9 min   no
15m-indices wyckoff US30    2         1    32     17 min        17 min   no
15m-indices wyckoff USTEC   2         1    32      9 min         9 min   no
15m-indices wyckoff DE40    2         1    32      8 min         8 min   no
15m-indices wyckoff FRA40   2         1    32      9 min         9 min   no
total shards: 212; modelled runner minutes: 40485
```
