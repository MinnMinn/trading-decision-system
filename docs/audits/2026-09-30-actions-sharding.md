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
* `scope`: `cell`, `runner_method`, `timeframe`, `symbol`, `value_key`, and `series` = bar count, first and last bar of the
  PIT-truncated series the scan read (the FTMO history is committed, so this catches a changed history file cheaply).

`run` / `scan --wave 2` REFUSE (`ScanCacheRefused`, exit non-zero, nothing evaluated) on: a stamp difference (message names the
differing field, e.g. `code.scripts/fund-search.py` or `plan_hash`); a `series` that differs from what the engine itself loaded; a
file that is torn / not JSON / structurally incomplete; a file whose name or recorded key does not match its content hash (renamed,
edited, foreign); a `trades_sha256` or `n_trades` mismatch (tampered); two entries for the same (value set, symbol) that disagree;
a missing cache directory; and, for `--wave 2`, an **incomplete wave 1** (the wave-2 sets would be chosen from a partial pool).
Entries of another cell/method/timeframe made by the *same* code are ignored, not used. `write_scan_entry` refuses to write trades that
do not survive a JSON round trip unchanged (type, key order, float text), so a cache can never alter a trade.

## 3. Time estimates

**Model** (`SHARD_MODEL`, `shard_seconds` in `scripts/fund-search.py`; `list-scan-shards --explain` prints the full table):

* MEASURED (owner, given): 581 s first set, ~213 s each further set, ICT XAUUSD 1m, 39 sets, 10 workers (= 8,675 s = 2.41 h).
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
  drops more series to in-process. I could not check the repository's visibility.

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

**Cost, honestly:** modelled total ~**706 runner-hours** (42,383 shard-minutes, 244 jobs), of which 1m-metals is ~592 (ICT ~212, Wyckoff ~380).
Critical path with unlimited concurrency: wave 1 (<= ~4.6 h) then wave 2 (<= ~4.6 h) then evaluate, i.e. ~10 h wall; your plan's concurrent-job
limit stretches that (I did not look it up). `scan_many` returns all the sets of one slice at once, so a
shard killed at the timeout loses its own slice, not the others (`Re-run failed jobs` repeats only the failed shards; a present entry is verified and skipped).

**Evaluate job:** with a complete cache it does no scans; what remains is loading both symbols' series (1m metals ~2 x 3.4 GiB by the audit's
per-bar figure, fits 16 GiB but not measured here), adx indices, `trades_for` post-processing and `dataset_snapshot` hashing. Not measured; expected minutes,
not hours, but this is an estimate.

## 4. Workflow (`.github/workflows/fund-search.yml`)

`workflow_dispatch` only, `permissions: contents: read`, inputs and matrix values only via `env:` (validated in the script; the existing
`WorkflowHardening` test still passes), all outputs under `$RUNNER_TEMP` (outside the checkout, section 46), every job `timeout-minutes: 355`.
New jobs `scan_wave1` / `scan_wave2` upload `fund-scan-<cell>-<method>-<symbol>-w<wave>-s<slice>` (the requested
`fund-scan-<cell>-<method>-<symbol>` plus wave/slice suffixes, which are needed for uniqueness once a symbol has several slices).
`evaluate` downloads `fund-scan-<cell>-*` and runs `run --scan-cache`. `plan` also emits `list-scan-shards --wave 1|2`.

* **History root:** `main()` already does `os.environ.setdefault("BT_HISTORY_ROOT", data/history/ftmo)` before every command and `_load_bt`
  freezes it at exec, so `scan`, `run` and `plan` read the committed FTMO feed. The workflow also sets `BT_HISTORY_ROOT: ${{ github.workspace }}/data/history/ftmo`
  at workflow level, so no job can silently use another root. Costs come from the committed `data/history/costs/ftmo/`.
* **`fetch-depth: 0` added to every checkout that runs `plan`/`scan`/`run`.** `code_fingerprint()` is `git log -1 -- <file>` per pinned file; a depth-1
  clone (the default) contains one commit, so every file would report the same SHA and `run` would read as drift against a declaration made from full
  history. That is a defect of the pre-change workflow as well (I reasoned from git's shallow semantics; I did not run it in Actions).
* `evaluate` keeps default `needs` semantics on purpose: one failed scan shard skips the evaluate jobs instead of letting a cell fall back to an
  on-demand multi-hour scan that the 355-min cap would kill. Change to `if: !cancelled()` if partial evaluation is preferred.
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

`scripts/tests/test_fund_search.py`: `ScanCache` (real `BtEngine`, real ICT scan over a 7,000-bar US500 5m slice, 4 real grid items):
cache run == no-cache run (result JSON, `runs_evaluated`, trades `repr`, admission and edge rows; on-demand scanning forbidden while it runs), non-vacuous wave 2,
deterministic bytes, rerun skips, partial cache, partly cached symbols, refusal on code / plan / settings / history / tamper / dropped trade / torn / renamed /
missing directory / foreign entry, wave 2 refusing an incomplete wave 1, slice partition, `--out` inside the checkout, no declaration; `ShardLayout`; `ScanCacheRunPlumbing`.
The slice is far too short for selection to choose, so the tests wrap `select_values` (it still runs for real) to force "last candidate of every factor" and
guarantee a wave 2; the real selection path is exercised by the two-wave runs of `test_speed_equivalence`.
