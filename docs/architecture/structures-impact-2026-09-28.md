# A1 impact: one structure source (scripts/structures.py)

Plan item A1 (docs/plans/2026-09-28-methodology-improvement-plan.md §2); ADR 0009
(docs/adr/0009-2026-09-28-one-structure-source-for-decision-and-chart.md). CLAUDE.md §59 ten-item list, for the
change that added `scripts/structures.py` and re-plumbed `scripts/live_rules.py` (`read_at`) and
`scripts/backtest-methods.py` (`_wyckoff_candidates`) through it.

## What changed

- **New file** `scripts/structures.py`: wraps `scripts/ict-scan.py` `analyze()` and `scripts/wyckoff_rules.py`
  `detect_accumulations()` / `detect_distributions()` into a schema of plain, timestamped structure objects
  (`kind`, `formed_at`, `available_at`, plus the wrapped record's own fields). It calls the existing detection
  functions; it does not recompute detection. Full schema documented in the module's own docstring, including
  the confirmation-delay rules for pivots/pools/FVGs added in code review round 1 (below).
- **Additive fields on `ict_scan.analyze()`'s return dict** (`scripts/ict-scan.py`): `pivots_high`, `pivots_low`
  (the `sh`/`sl` 3-bar pivot index lists the function already computed but never returned) and `mss_all` (the
  full MSS list; the existing `mss` key keeps its display-only last-3 slice, unchanged). New keys only — every
  existing reader of this dict is unaffected.
- **Additive field on a pool record** (`scripts/ict-scan.py`'s `add()`): `to`, the LAST constituent pivot's bar
  index (`from`/`to` are the same for an "old" single-pivot pool; differ for an "equal" two-pivot pool). Added
  in code review round 1 so structures.py could compute a pool's confirmation delay correctly (below).
- **`scripts/live_rules.py` `read_at()`**: calls `structures.ict_analysis(w, recent, tf, methods=methods)` — the
  RAW pass-through (code review round 1, item 4: hot-path/cold-path split, below) — and returns it directly.
  Byte-identical to `ict_scan.analyze()`; see `scripts/tests/test_structures.py`
  `LiveRulesRoutesThroughStructures.test_read_at_matches_direct_analyze`.
- **`scripts/backtest-methods.py` `_wyckoff_candidates()`**: calls `structures.wyckoff_records(O, H, L, C, V,
  volume_kind=vkind, side=side)` — the RAW pass-through — and reads the returned list directly. Byte-identical
  to `W.detect_accumulations()` / `W.detect_distributions()`. Signature unchanged from before A1 (no `Tm`
  parameter — see code review round 1, item 4).
- **New tests**: `scripts/tests/test_structures.py` (24 tests; see Tests below).

### Code review round 1 (fix round 1 of 2, per rules/review-loop-limits.md)

1. **§8 confirmation-delay timestamps.** A pivot/pool/FVG is not knowable as soon as its OWN bar closes — the
   detection rule itself needs LATER bars. `pivot_high`/`pivot_low`: `available_at` is now `bar i + PIV` (the
   pivot half-width), not bar `i`. `fvg`: `available_at` is now `bar i + 1` (the gap needs bar `i+1`'s high/low),
   not bar `i`. `pool`: `available_at` is now the LAST constituent pivot's `to + PIV` (an "equal" pool's second
   matching swing is what actually confirms the level), not `from`'s. Non-tautological tests added
   (`ConfirmationDelay` in test_structures.py) using a synthetic window with a hand-placed, isolated
   pivot/pool/FVG verified independently of structures.py's own arithmetic, asserting `available_at` is
   strictly LATER than the (wrong) same-bar answer.
2. **Bias availability.** When `htf_context.ict_bias()` combines the prev-candle draw (always read from
   `window[-1]`, whichever state fires) and the MSS, `available_at` is now the LATER of the two contributing
   bars — the pre-fix bug (`bi = m["i"] if m else ...`) silently ignored the draw's `window[-1]` read whenever
   an MSS was also present. New test `BiasAvailability.test_draw_and_mss_combine_available_at_is_the_later_bar`
   exercises the real draw+MSS branch on AUS200 4H data.
3. **Pool objects carry formation fields only.** `state`/`swept`/`closed_at` are determined by a FORWARD scan
   over bars strictly after the pool formed; stamping them onto an object timestamped at the pool's own
   formation bar would silently attach future information to a past timestamp. They are removed from the
   `pool` structure object (which now carries `pool_kind`/`level`/`from`/`to`/`type` only) — that information
   already lives on the separately, correctly timestamped `sweep`/`closed_through` objects.
4. **Hot-path / cold-path split.** `read_at()` and `_wyckoff_candidates()` run once per bar/window in a
   backtest and never read the enriched structure objects — only `env["analysis"]`/`env["records"]`. Building
   the full envelope on every call was pure waste. `structures.ict_analysis()` / `structures.wyckoff_records()`
   are RAW pass-throughs (literally the wrapped call) that the hot path now uses; `ict_structures()` /
   `wyckoff_structures()` (unchanged) remain available for callers that want the typed objects. A further fix
   in this item: `live_rules.py` was loading its own separate copy of `structures.py` via the
   spec_from_file_location workaround (needed for dash-named files, NOT needed for `structures.py`), which
   caused `ict-scan.py`/`htf_context.py` to be reloaded a third time per process; changed to a regular
   `import structures`, sharing the one instance `backtest-methods.py` already imports. Measured:
   micro-benchmark (in-process, interleaved, warmed up) showed the wrapper functions add ~0.02% overhead —
   statistically zero; the full `stability-report.py --symbols XAUUSD --tf 1H --workers 1` wall-clock, after
   the import-sharing fix, is +0.86% vs. base (3 base samples, 2 post-fix worktree samples) — within the 3%
   budget. See `$TMP/a1-perf.log` for the full investigation, including the pre-fix measurement that exceeded
   budget and the root-cause diagnosis.
5. **Extended byte-identity evidence.** BTCUSDT (crypto) 1H added to the rows comparison (`$TMP/a1-rows.log`),
   run against the fully round-1-fixed code: 9/9 rows byte-identical, base vs. worktree.

## Why re-plumbing stopped where it did

ADR 0009 requires ONE structure source for ICT (pivots, pools with state, sweeps, MSS, FVGs, dealing range,
bias) and Wyckoff (trading range and events). Both are produced by exactly ONE call site each in the decision
path:

- ICT: `scripts/live_rules.py` `read_at()` is the only place `ict_scan.analyze()` is called for a live/backtest
  decision. `scripts/backtest-methods.py` `ict_setups_live()` and `scripts/strategy-runner.py`
  `ict_live_setups()` both obtain `a` from `live_rules.read_at()` and pass it to
  `lr.ict_scan.setup_candidate(a, ...)` — a Setup-domain computation (CLAUDE.md §14), not a Structure, and
  outside A1's list. Routing `read_at()` through `structures.py` therefore routes every consumer transitively.
- Wyckoff: `scripts/backtest-methods.py` `_wyckoff_candidates()` is the only place
  `wyckoff_rules.detect_accumulations()` / `detect_distributions()` are called for a live/backtest decision.
  `scripts/strategy-runner.py` `setups_wyckoff()` delegates entirely to `bt.wyckoff_fires()`, which calls
  `_wyckoff_candidates()`. Routing that one function through `structures.py` therefore routes every consumer
  transitively.

No other production code path calls `analyze()` / `setup_candidate()` / `detect_accumulations()` /
`detect_distributions()` directly (verified by grep of every importer of `ict-scan.py`, `wyckoff_rules.py`,
`live_rules.py` — see Consumers below). `scripts/build-artifact.py` and `scripts/chart.js` (A2) currently run
their OWN, separate ICT detector and model-read Wyckoff overlay per the fidelity audit ADR 0009 cites; they are
explicitly out of scope for A1 and untouched here.

## 1. Consumers

Grepped every importer of `ict-scan.py`/`ict_scan`, `wyckoff_rules.py`, `live_rules.py`:
`automation.py`, `backtest-methods.py`, `build-artifact.py`, `check-narrative.py`, `diagnose-methods.py`,
`evidence.py`, `htf_context.py`, `ict-scan.py`, `instruments.py`, `live_rules.py`, `method-panel.py`,
`mt5_time.py`, `normalized.py`, `pit.py`, `providers.py`, `snapshot.py`, `stability-report.py`,
`strategy-runner.py`, `win_services.py`, `wyckoff_rules.py`, plus 20 test modules.

| Consumer | Calls `analyze()`/`detect_*()` directly? | Routed through `structures.py`? |
|---|---|---|
| `live_rules.py` `read_at()` | yes (was direct) | **yes — edited** |
| `backtest-methods.py` `_wyckoff_candidates()` | yes (was direct) | **yes — edited** |
| `backtest-methods.py` `ict_setups_live()`, `wyckoff_fires()` | no — reads `live_rules.read_at()` / `_wyckoff_candidates()` | transitively, unedited |
| `strategy-runner.py` `ict_live_setups()`, `setups_wyckoff()` | no — reads `bt.lr.read_at()` / `bt.wyckoff_fires()` | transitively, unedited |
| `htf_context.py` `ict_bias()`, `wyckoff_bias()`, `bias_of()` | no — takes an already-computed `facts`/`wyckoff` dict as an argument | consumed by `structures.ict_structures()`'s `bias` field; unedited |
| `check-narrative.py` | no — reads `wyckoff_rules.PARAMS/COMMIT/VOL` constants and calls `htf_context.ict_bias()`/`wyckoff_bias()` on model-provided narrative text, not on structure detection | unaffected, unedited |
| `build-artifact.py` | no hits — chart.js owns its own ICT detector today (ADR 0009 problem statement) | **A2 scope, not this task** |
| `diagnose-methods.py` `WyProbe`/`IctProbe` | monkeypatches `bt._wyckoff_candidates`/`lr.read_at` from outside | unedited (both signatures are unchanged from before A1, per the hot-path/cold-path split, code review round 1 item 4); patches still take effect on the shared `wyckoff_rules`/`structures` module singletons |
| `automation.py`, `evidence.py`, `instruments.py`, `method-panel.py`, `mt5_time.py`, `pit.py`, `providers.py`, `snapshot.py`, `win_services.py` | no — string/comment references only (grep-verified) | unaffected |
| `local-eval-brief.py` | no hits | unaffected |

## 2. Providers

No provider (market-data source, execution venue) is touched. `structures.py` reads only the candle windows its
callers already hand it; it does not open a new data source or change `normalized.py`'s provenance/quality
model.

## 3. Persistence impact

None. `structures.py` writes nothing to disk. `ict-scan.py`'s `main()` (the `data/live/prelim/*.facts.json` /
`*.meta.json` writer) is unchanged — it still calls `analyze()` directly, not through `structures.py`, and its
output format is unchanged (the two additive `analyze()` keys, `pivots_high`/`pivots_low`/`mss_all`, are not
read by `facts_entry()` or written to `facts.json`).

## 4. API impact

None (no HTTP-exposed endpoint in this codebase's current phase).

## 5. UI impact

None. This is A2's task (rendering structures.py's objects on the chart); the chart still reads its own
detector (chart.js) and the model-read narrative overlay, unchanged.

## 6. Test impact

- New: `scripts/tests/test_structures.py` (24 tests, after code review round 1 — see Tests below).
- `scripts/diagnose-methods.py` was touched during round 1's investigation (briefly gained then lost a
  `_wyckoff_candidates` `Tm` parameter as the hot-path design iterated) and ends this round unchanged from
  before A1, since item 4's final design needs no signature change there.
- Every existing test module that imports `ict-scan.py`, `wyckoff_rules.py`, `live_rules.py`, `htf_context.py`,
  `backtest-methods.py`, or `strategy-runner.py` was run; see Tests below for the full list and results.

## 7. Backtest impact

None intended, and verified: `scripts/stability-report.py --symbols AUS200,XAUUSD --tf 4H,1H --workers 1` and
(code review round 1, item 5) `--symbols BTCUSDT --tf 1H --workers 1` all produce identical `rows` on the base
commit (db3c0bb) and in this worktree — see Tests below. A1 is a refactor; it must not change a single trade,
and the byte-identity checks (unit-level in `test_structures.py`, and full-backtest-level via
`stability-report.py`) are the evidence for that. Performance (code review round 1, item 4): the hot path
(`read_at()`/`_wyckoff_candidates()`) measures within a 3% wall-clock budget vs. base after the import-sharing
fix — see `$TMP/a1-perf.log`.

## 8. Research-semantics impact

None. No detection rule, threshold, or output changed. The two additive `analyze()` fields (`pivots_high`,
`pivots_low`, `mss_all`) expose data the function already computed internally; they do not change what is
computed, only what is returned. `structures.py`'s own transformations (grouping into `kind`/`formed_at`/
`available_at` objects) are read-only views over the same values.

## 9. Migration impact

None. No data migration, no schema version bump, no `SNAPSHOT_INPUTS_VERSION` change in
`scripts/normalized.py` (A1 does not alter what `available_time()` means or how a stored series is
interpreted — it only calls that existing function once per structure object instead of not calling it at
all).

## 10. Versioning impact

A1 is declared in the plan as byte-identical and is NOT Trading System version significant (CLAUDE.md §47):
no required-analysis, methodology, setup, risk, news, or decision-ordering semantics changed. This is the
refactor step the plan's Workstream A groups separately from the F/V methodology changes in Workstream B,
which DO carry their own version notes.

## What A1 does NOT do (declared out of scope, left for later plan items)

- **A1b** (new objects): Wyckoff phase labels, `invalidated_at` for pools/FVGs, and higher-timeframe Wyckoff
  trading-range detection (WA2-19) are NOT added here. `structures.py`'s Wyckoff wrapper only carries the
  fields `detect_accumulations()`/`detect_distributions()` already compute.
- **A2** (render): `scripts/build-artifact.py` and `scripts/chart.js` are untouched. The chart still runs its
  own ICT detector and the model-read Wyckoff overlay (anchors, narrative TR/events) — the exact ADR 0009
  problem statement — until A2 re-points the chart at `structures.py`'s objects.
- **A2b** (staleness → WAIT/BLOCK): not touched.
- Full re-derivation of `backtest-methods.py`'s ICT/Wyckoff gate logic (`_fires_from`, `ict_setups_live`) to
  consume `structures.py`'s normalized objects directly (rather than the raw `analyze()`/`detect_*()` dicts
  `structures.py` also exposes unchanged via `env["analysis"]`/`env["records"]`) was assessed and NOT done: the
  gate logic (`r["bu"]`, `r["reclaim"]`, `su["entry_models"]`, dozens of direct dict-key reads across hundreds
  of lines) would need to be rewritten against the new schema, which is a behavior-preserving-but-large change
  outside what could be verified byte-identical with confidence in this task. `structures.py` IS in the
  decision path (both `read_at()` and `_wyckoff_candidates()` call it), which satisfies ADR 0009's "one
  structure source" for detection; the gate/setup logic reading the raw records unchanged is a separate,
  lower-risk follow-up.

## Tests

Evidence paths (all under the scratchpad TMP the dispatch prompt named):
- `$TMP/a1-tests.log` — sequential run of every existing test module that imports the touched files, plus a
  consolidated summary of results and pre-existing-vs-regression classification for every failure.
- `$TMP/a1-test-structures.log`, `$TMP/a1r2-test-structures-final.log` — `scripts/tests/test_structures.py`,
  24/24 pass (post code review round 1).
- `$TMP/a1-test-diagnose-methods-rerun.log` — `test_diagnose_methods.py` pass (7/7).
- `$TMP/a1-test-live-rules-full.log`, `$TMP/a1r2-test-live-rules.log` — `test_live_rules.py` full runs, 39/39
  pass each (one pre-existing slow test, confirmed equally slow on base commit db3c0bb, not an A1 regression).
- `$TMP/a1r2-consumer-subset-final.log` — 347 tests across 10 fast consumer modules, OK (post code review
  round 1, after the import-sharing fix).
- `$TMP/a1-perf.log` — code review round 1, item 4: performance investigation and result (+0.86%, within the
  3% budget after the import-sharing fix; includes the pre-fix measurement that exceeded budget and its root
  cause).
- `$TMP/a1-rows.log` — `stability-report.py --symbols AUS200,XAUUSD --tf 4H,1H --workers 1` `rows` byte-identity
  (base db3c0bb vs this worktree): 18 rows both sides, deep-equal. Raw JSON: `$TMP/a1-stability-before.json`
  (base) and `$TMP/a1-stability-after.json` (worktree).
- `$TMP/a1-replay.log` — `strategy-runner.py --replay all --bars 900` output, byte-identical (`[]` both sides;
  the log explains why `[]` is the correct, expected result given zero enabled setups in
  `docs/architecture/pilot-selection.json`, and points to the stronger stability-report proof for actual
  trade-generation byte-identity).
