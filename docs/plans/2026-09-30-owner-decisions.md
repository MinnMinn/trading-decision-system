# Owner decisions recorded during Batch 1-2 (2026-09-29 / 2026-09-30)

Source: chat with the owner; recorded here so they survive a context reset. Supplements plan §6
(docs/plans/2026-09-28-methodology-improvement-plan.md). Nothing here loosens any §1.4 rule.

## Adopted F set for the evaluation baseline (owner: "Cho phép adopt", 2026-09-30)
Adopted on the default proposal (F items whose funnel trade-count delta is within x1.5, plan §1.2):
- ICT: `fx_b2a_fvg_in_leg` (B2a), `fx_b2b_ce_fail` (B2b).
- Wyckoff: `fx_w1_tr_low_st` (W1), `fx_w3_mSOW_spring` (W3), `fx_w5_vp_abandon` (W5).
Evidence: docs/audits/2026-09-29-ict-fidelity-funnel.md, docs/audits/2026-09-29-wyckoff-fidelity-funnel.md.
ALSO ADOPTED by explicit owner instruction 2026-09-30 ("Đồng ý adopt B-RAID, W2, B1 và W7"), despite trade-count deltas beyond
x1.5 (B-RAID ~x9, B1 x2.07 on DE40, W2 x1.63 on XAUUSD) and W7 acting on ~80 % of Wyckoff trades: `fx_braid_optional`,
`fx_b1_pivot1`, `fx_w2_st_below_sc`, `fx_w7_htf_target`. The reviewer's B-RAID recency suspicion was tested and rejected
(docs/audits/2026-09-29-ict-fidelity-funnel.md); a lookback bound was added on the no-raid path, effect ~0.
So all nine F items are in the evaluation baseline. `fx_a2b_stale_htf_block` (A2b) is a live-safety key, default OFF; its
adoption is a separate live-safety decision.
"Adopted" means: ON in the evaluation baseline of the fund search only. The live/pilot path keeps v1 until the owner
approves v2 (plan §1.6). The evaluation harness must set the nine F keys in its fixed overlay before any run.

## V-item readings (defaults accepted 2026-09-29)
- W4a: baseline = key unset (v1's own typing, not a count); the cells 3 and 4 are the variants. An explicit `2` is a different rule.
- W-TOUCH: at least 2 recorded Phase-B tests at each TR border (`W_TOUCH_MIN = 2`).
- W6: only the Wyckoff-side key; decided together with the ICT SCAN_WINDOW; a 600-bar window needs >= 600 bars.
- B-POOL: most recent completed UTC day (PDH/PDL) plus the most recent completed asia/london run.
B4 (ICT) and W4b (Wyckoff) are declared but not implemented (the sources define no engine-usable rule); they stay counted in N.

## Execution / MT5 MCP
- Order placement through the MT5 MCP is permitted (owner, 2026-09-29). The system is built to trade real accounts, so there
  is NO hard-coded demo-only block. Real money is selected only by the explicit environment switch, never by default, and
  every order still passes the risk check (1 %), event-risk, account rules and human confirmation (CLAUDE.md §51).
- The forward-demo go-ahead and the pilot remain a separate explicit owner decision; the pilot stays OFF.
- The MT5 MCP key lives only in config/env.demo (gitignored). The key that appeared in chat is compromised and must be rotated.
  MCP research: docs/architecture/mt5-mcp-evaluation.md (official docs do not describe auth; key sharing "not documented").

## Compute plan (owner: "(b) rồi (a)")
(b) first: make the scan engine fast enough to run cells locally (multi-value-set reuse, parallelism), byte-identical results.
(a) then: shard the fund search on GitHub Actions by value set/symbol. Pushing/triggering workflows needs the owner's go-ahead
at that time.

## Standing rules restated
- The evaluation window is never moved to rescue a method. Results are reported honestly, including zero passes.
- The engine smoke test (docs/audits/2026-09-30-fund-search-engine-smoke.md) is structural only and does not count as an evaluation.

## 2026-09-30 (later): planned R:R floor 2.5, `no_floor` removed, minimum edge `e`
1. **Planned R:R floor at entry = 2.5** (owner: "R:R target when entering a trade must be at least 2.5R"), for BOTH methods
   (ICT and WYCKOFF-BOOK) and BOTH backtest (`simulate()`) and live (`strategy-runner` `rr_reason`), applied NET of fees
   exactly as before. Source of truth: `docs/architecture/analysis-params.json` `project_defined.ict.min_rr` (was 2.0 since
   2026-09-19, 3.0 from 2026-09-13; the history stays in its `_basis`). One reader: `trading_env.min_rr()`.
2. **`no_floor` removed from the ICT V grid** (`docs/architecture/v-grid-ict.json`, item B-EXIT): it skipped the planned-R:R
   floor for ICT trades, which contradicts decision 1. B-EXIT is now 3 x 4 x 1 = 12 value sets (11 non-baseline). The engine
   code path for a `no_floor` token is kept (live never sets `fx_` keys), but no grid cell can reach it (`build_overlay`
   refuses a value the grid does not declare).
3. **New N.** ICT: 1 + 27 + 1 = **29 per cell** (was 41), x 8 cells = **232** (was 328), one-sided confidence
   1 - 0.10/232 = **0.999569** (was 0.999695). Wyckoff unchanged: 16 per cell, 128, 0.999219.
   (`python3 -W ignore scripts/fund-search.py plan --dry-run`.)
4. **The declaration pins the floor.** `evaluation_config.min_rr` (scripts/fund-search.py) is written by `declare`; `run`
   refuses on drift if the effective floor differs. `scripts/fund-search.py` is a pinned file, so `declare` must run after this change.
5. **`e` (minimum edge of interest).** Delegated by the owner and set by the coordinator to **0.20R** as a
   pre-declaration default. It is to be fixed before `declare` and is not adjustable after results are seen.


## 2026-10-01: cell list and per-cell history spans (owner, in chat; binding)
Source of the numbers: `docs/audits/2026-10-01-trade-rates.md` (branch `b10-trade-rates`; trade COUNTS only, no performance figure read).
The decisions were taken on compute cost and statistical power, NOT on performance.

1. **Per-cell history spans become a DECLARED, pinned part of the plan.** `docs/architecture/fund-search-cells.json` lists the cells and each
   cell's optional `dev_start` (null = the cell starts at the first bar its data has). It is read by `plan`, hashed into the plan core (`plan_hash`
   changes), pinned in the declaration as `evaluation_config.cells_sha256` (+ `dev_start_by_cell`, `span_warmup_days`) and `run`/`scan` refuse a
   changed file, exactly like the V grids. The development cutoff (2024-03-01) and the fold geometry (`make_folds`: 365-day test folds, >= 730 days
   of training) are unchanged; only the START of a cell's decision-timeframe data can move.
   **Outcome of the owner's final choice: every cell keeps its ORIGINAL data start** (the owner first offered 2018-03-01 for 1m-metals, 2020-03-01
   for 1m-indices and 2008-03-01 for 5m-metals, then WITHDREW all three the same day -- reason: Wyckoff 1m is feasible after the speed-ups, compute is not the binding constraint; 5m-indices, 15m-metals, 15m-indices were never shortened).
   So `dev_start` is null in all six cells and the fold counts are 1m-metals 9, 1m-indices 4, 5m-metals 17, 5m-indices 4, 15m-metals 17, 15m-indices 4.
   The mechanism exists and is tested for a future declared start: the engine scans decision bars only from `dev_start` minus `warmup_days` (14) minus the
   method's own window, discards every trade entered before `dev_start`, and leaves higher-timeframe series (gates, W7) at their full PIT history.
   Any future non-null `dev_start` must re-run `scripts/research/span_equivalence.py` for its cell. Trade counts and power: `docs/audits/2026-10-01-trade-rates.md`, `docs/audits/2026-10-01-power-model.md`. Proof that a cut series gives the full-series trades: `scripts/research/span_equivalence.py` (ICT US500 5m, Wyckoff XAUUSD 15m; see the
   evidence in the commit message and `EngineDevStart` in `scripts/tests/test_fund_search.py`).
2. **The two 30m cells (`30m-metals`, `30m-indices`) are REMOVED** for both methods (underpowered). 15m cells are kept. Remaining cells: 1m-metals,
   1m-indices, 5m-metals, 5m-indices, 15m-metals, 15m-indices = 6 cells x 2 methods = 12 candidates.
3. **New N** (`python3 -W ignore scripts/fund-search.py plan --dry-run`): ICT 29 x 6 = **174**, one-sided confidence 1 - 0.10/174 = **0.999425**
   (was 232, 0.999569); Wyckoff 16 x 6 = **96**, 1 - 0.10/96 = **0.998958** (was 128, 0.999219). Plan hash
   `f7d67a77ef1e9e20` (first 16 hex; changes with any edit to the cells file, the grids or the first-bar data). [That hash was for the cells file of
   that commit; the symbol lists added the same day (section 'Owner decisions 2026-10-01 (symbol universe)' at the end) change the cells file, so
   plan_hash changes again. N, cell count and the fold counts above are unchanged.]
4. **Expected TEST trades for the final spans (MODEL, not measurement)** = the trade-rates doc's mean pooled trades per year (baseline value set, slices
   S1-S3 for metals, S2-S3 for indices) x the test folds of the cell (one fold = 365 days). The `n_req` figures (ICT 760, Wyckoff 690; 2x for a design effect of 2) are
   the coordinator's model of that doc and were derived at the OLD N (232 / 128); they are NOT recomputed for N = 174 / 96 here. The metals rates are extrapolated
   to the earlier folds (the doc says so).

   | method | cell | rate /yr | test folds | expected TEST trades | >= n_req (1x)? | >= 2 x n_req? |
   |---|---|---|---|---|---|---|
   | ICT | 1m-metals | 675.7 | 9 | 6081 | yes | yes |
   | ICT | 1m-indices | 1849.5 | 4 | 7398 | yes | yes |
   | ICT | 5m-metals | 112.3 | 17 (14 if it had started 2008-03-01) | 1910 (1572) | yes (yes) | yes (yes) |
   | ICT | 5m-indices | 335.0 | 4 | 1340 | yes | no |
   | ICT | 15m-metals | 35.3 | 17 | 601 | no | no |
   | ICT | 15m-indices | 100.0 | 4 | 400 | no | no |
   | Wyckoff | 1m-metals | 448.7 | 9 | 4038 | yes | yes |
   | Wyckoff | 1m-indices | 1213.0 | 4 | 4852 | yes | yes |
   | Wyckoff | 5m-metals | 112.7 | 17 (14) | 1915 (1578) | yes (yes) | yes (yes) |
   | Wyckoff | 5m-indices | 257.5 | 4 | 1030 | yes | no |
   | Wyckoff | 15m-metals | 45.3 | 17 | 771 | yes | no |
   | Wyckoff | 15m-indices | 92.5 | 4 | 370 | no | no |

   The two removed cells, for the record (same doc): ICT 30m-metals 210 and 30m-indices 216 expected test trades, Wyckoff 181 and 90, all below n_req.
   5m-metals reaches n_req and 2 x n_req at either 17 or 14 folds (model), so by the model the fold count of 5m-metals is not what limits its power.
   The 15m cells stay although the model shows them below n_req (ICT 15m-metals and 15m-indices, Wyckoff 15m-indices); that is disclosed here, and the evaluation reports whatever it finds.
5. **Pinned files changed by this decision** (`FINGERPRINT_FILES`): `scripts/fund-search.py`, `scripts/backtest-methods.py` (the `series_start` load seam, default
   no-op), `scripts/scan_many.py` (hands the seam to its spawned workers). `declare` must run after this change (the declaration fingerprints these files).


## Owner decisions 2026-10-01 (symbol universe) (owner, in chat; binding)
Design and code points: `docs/plans/2026-10-01-symbol-universe-design.md`. Taken on statistical power (more symbols, hence more pooled trades, in the
under-powered 5m and 15m cells), NOT on performance. The history and real-cost specs of the new symbols are exported from MT5 by the owner;
until they exist `scripts/fund-search.py plan --check-data` prints which cell lacks what and exits 1, and `plan`/`run`/`scan`/`declare` refuse with the same table.
The owner's list changed three times the same day; this entry records the FINAL one.

- **(a)** Symbols are added to the **5m and 15m cells only**. The two 1m cells are unchanged (1m-metals XAUUSD XAGUSD; 1m-indices US500 US30 USTEC DE40 FRA40).
- **(b)** 5m-metals and 15m-metals = XAUUSD XAGUSD + **XPTUSD XPDUSD** (4 symbols; XPT/XPD history from 2015-01-07). The cross-quoted XAUEUR XAUAUD XAGEUR XAGAUD are not added (same underlying).
- **(c)** 5m-indices and 15m-indices = US500 US30 USTEC DE40 FRA40 + **UK100** (from 2017-12-28), **EU50** (2017-12-29), **JP225** (2017-12-28), **HK50** (2018-12-17),
  **AUS200** (2019-02-08; it already has a spec in `data/history/costs/ftmo`), **US2000** (2018-01-23), **SPN35** (2020-11-09), **N25** (2020-11-12) = 13 symbols. Raw MT5 names are `<X>.cash`; canonical names strip `.cash`.
- **(d) Considered and dropped for lack of pre-cutoff history** (their first bars are after the 2024-03-01 development cutoff, so they have zero development data): **XCUUSD** (copper, history from 2024-12-02) and **DXY** (`DXY.cash`, FTMO path 'Cash III CFD', history from 2024-11-26; note that DXY is a *currency* index, not an equity index, so it would have been classified `indices` only for lack of another class).
- **(e) Parked by the owner, "for now" (not rejected):** all FX (28 pairs: would need an `fx` asset class and `5m-fx` / `15m-fx` cells, which are NOT in the code; the `ForexWasRemovedCleanly` guard in `scripts/tests/test_instruments_sync.py` is untouched), crypto, energies, stocks, exotics.

**Plan: unchanged at 6 cells** (1m-metals 2 symbols, 1m-indices 5, 5m-metals 4, 5m-indices 13, 15m-metals 4, 15m-indices 13) = 12 candidates (method x cell). More symbols in an existing cell add no N.
**N: ICT 29 x 6 = 174 (confidence 1 - 0.10/174 = 0.999425); Wyckoff 16 x 6 = 96 (0.998958)**, as before this entry. `plan --check-data` prints it from the declared cells (no data needed); `plan --dry-run` prints the same once every cell has data.
**plan_hash changes** (the cells file is hashed into it) and can only be computed once the data exist. Cells-file sha256 at the commit that made this change: printed by `plan --check-data`.

**Registry.** `docs/architecture/instruments.json`: nine symbols (XPTUSD XPDUSD UK100 EU50 JP225 HK50 US2000 SPN35 N25) were added to `canonical`, `display` (asset_class `metals` / `indices`) and `analysis.cfd`, and are listed in the new
`research_only.cfd` list. They are **research-only: never on `execution` or `backtested`** (`scripts/instruments.py` refuses to load a research-only symbol that is orderable). The live surfaces (scanner config, live page, method panel, local-eval-brief) and
`scripts/prop-search.py` read `instruments.live_analysis()` = analysis minus research-only, so they behave as before; prop-search's pre-registered candidate space stays **180** (candidate-list hash `8137a8b1...` identical to f5eb338, pinned by a test).
`AUS200` was already on the registry (and on `execution.cfd`, which this work does not touch); it is one of prop-search's 180 candidates, so it is NOT marked research-only. `data/history/costs/ftmo/symbol-map.json` maps the nine raw names.
Open (design doc E.2): the cost profile `ftmo_demo_2026_09` now also covers specs exported in 2026-10; the symbol-map hash recorded in a run's `profile_snapshot` differs from before (no declaration exists yet, so no drift).

**Late-starting symbols: how the stability rule treats them (code: `scripts/fund_stats.py` `make_folds`, `check_stability`; `scripts/fund-search.py` `build_cells`; thresholds unchanged).**
- A cell's development start is the first bar of its EARLIEST symbol with data; the folds (365-day test folds, at least 730 days of training) follow from that date only. A symbol enters `m` iff it has a first bar BEFORE 2024-03-01; one that does not is left out of `m` and disclosed (`symbols_without_development`). A symbol that starts later than the cell is kept in `m` and disclosed in `symbol_first_bar`.
- Stability = net expectancy > 0 on at least `ceil(2m/3)` of the `m` symbols, evaluated on the POOLED test trades of all folds. m = 2 -> 2, 4 -> 3, 13 -> 9. A symbol with no trade, or with a pooled mean <= 0, is not positive; it is never dropped from `m` and never re-weighted.
- 5m-indices / 15m-indices (4 test folds, 2020-03-02 .. 2024-03-01): UK100 JP225 EU50 US2000 HK50 AUS200 have data in every test fold and at least 388 days of history before fold 0 (AUS200, the latest of the six). SPN35 (2020-11-09) and N25 (2020-11-12) have data in all four folds but only from Nov 2020 in fold 0 (about 110 of its 365 days) and NO history before fold 0: they only contribute test trades, and fold 0's training trades come from the other 11 symbols. With m = 13 up to 4 symbols may be non-positive (need 9): SPN35 and N25 have the fewest trades (about 3.3 years of data), so the noisiest pooled means, and they count against the share if their mean is <= 0.
- 5m-metals / 15m-metals (17 test folds, 2007-03 .. 2024-03; folds follow XAUUSD from 2004-06-11): XPTUSD and XPDUSD (2015-01-07) have NO data in test folds 0-6, about 2 months of fold 7 and all of folds 8-16. They stay in m = 4 (need 3 positive of 4) and contribute test trades only to folds 7-16. A fold in which only some symbols have bars is judged on those trades (fold sufficiency and frequency are pooled over the fold's symbols).
- Not changed: any statistical threshold, grid, cost rule, `min_rr`, `FUND_SYMBOLS` order semantics.

**Not done here (named):** `DEV_BARS` in `scripts/fund-search.py` (shard sizing, part of the shard-calibration work) has no row for the new symbols, so `list-scan-shards` needs them once the data exist; the new specs' swap mode and commission are unchecked (design doc A.3 rows 7 and 8); US2000 1W and the specs are being re-exported (the readiness table will keep flagging them until they are on disk).

**Pinned changes: `declare` must run AFTER this change.** `scripts/fund-search.py` and `scripts/prop-search.py` are in `FINGERPRINT_FILES` and `docs/architecture/fund-search-cells.json` is pinned by its sha256 (`evaluation_config.cells_sha256`); all three changed here, so the declaration (not yet made) must be made on top of this change, and any later edit to them is drift.
**Live surfaces.** Research-only symbols are kept off every live reader: `instruments.live_analysis()` / `instruments_live_analysis` (bash) feed the scanner config and its REFUSED message (`scripts/automation.py`), the live page, the method panel, `scripts/local-eval-brief.py`, `scripts/trading_system.py` (`describe`), the SessionStart hook (`scripts/session-safety-rules.sh`, output byte-identical to f5eb338) and `/analyze` (`.claude/commands/analyze.md` refuses a `research_only` symbol). Tests: `test_instruments_sync`, `test_method_panel`, `test_trading_system`.
**Known state of tests / code.** The hardcoded-symbol-set test in `test_instruments_sync` was already red at f5eb338 (5 offenders); it now lists 6 (the multi-line `FUND_SYMBOLS` constant adds lines; `DEV_BARS` and diagnose-methods.py:42 are the old ones). In `build_cells` the 'no history file' exclusion branch cannot be reached with real data: the readiness gate (`DataNotReady`) refuses first; it stays for injected-`first_bar` tests. `plan --check-data` shows both the declared symbol count and the effective m (symbols with development data), since m, not the declared count, is the stability denominator.
