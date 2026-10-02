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
> SUPERSEDED in part by the section 'Owner decisions 2026-10-01 (cell selection: three cells)' at the end: the plan now has three cells (N 87 / 48). The text below is the record of the six-cell state.
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
> SUPERSEDED in part by 'Owner decisions 2026-10-01 (cell selection: three cells)' at the end: only 5m-metals keeps added symbols (XPTUSD XPDUSD); the 13-symbol index cells and 15m-metals are removed and their symbols parked.
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


## Owner decisions 2026-10-01 (cell selection: three cells) (owner, in chat; binding; supersedes the six-cell plan above)
Evidence: `docs/audits/2026-10-01-cell-selection.md` (branch `b16-cell-selection`; counts and a power model, NOT performance). The two entries above stay as written for the record; where they say "6 cells", "N 174 / 96", "5m-indices / 15m-metals / 15m-indices in the plan", this entry replaces them.

**The rule (pre-stated, owner approved BEFORE the measurements).** A cell is INCLUDED iff `e_min <= k x e_star` for at least one of {ICT, WYCKOFF-BOOK}, k = 2, primary pooling variant. `e_min` = smallest net edge (R/trade, binary +2.5/-1, cost 0.07R) at which the harness's own lower-bound rule has power >= 0.80 at the N-adjusted confidence; `e_star` = smallest net edge with `prop_pass_probability >= 0.70` on the binding fund (120-day horizon).

**Result (best ratio e_min/e_star over the two methods; N of the 8-cell candidate set, ICT 232 / Wyckoff 128; table T5 of the audit):**

| cell | best ratio | <= 2 ? |
|---|---|---|
| 1m-metals | 0.87 (ICT; Wyckoff 0.90) | yes |
| 1m-indices | 1.28 (both methods) | yes |
| 5m-metals | 1.26 (Wyckoff; ICT 1.60) | yes |
| 5m-indices | 3.76 (ICT; Wyckoff 4.41) | no |
| 15m-metals | 2.23 (Wyckoff; ICT 2.39) | no; ICT also fails the insufficient-fold guard, P(every test fold >= 30 trades) = 0.00 |
| 15m-indices | 6.21 (ICT; Wyckoff 7.59) | no |
| 30m-metals | 4.73 (both) | no |
| 30m-indices | e_min not reached by e = 1.0 | no |

At the final N (87 / 48, audit table T7) the included set is unchanged (ratios 0.73 / 0.90, 1.14 / 1.02, 1.40 / 1.26); 15m-metals is 2.22 (ICT) / 2.04 (Wyckoff), still above 2; 5m-indices 3.01 at best.

**Decision.** The plan keeps exactly THREE cells: `1m-metals` (XAUUSD XAGUSD), `1m-indices` (US500 US30 USTEC DE40 FRA40), `5m-metals` (XAUUSD XAGUSD XPTUSD XPDUSD). `dev_start` is null in all three (from data); fold counts 1m-metals 9, 1m-indices 4, 5m-metals 17.
**Removed** (recorded with reason, reference and decision in `removed_cells` of `docs/architecture/fund-search-cells.json`): 5m-indices (3.76), 15m-metals (2.23), 15m-indices (6.21), 30m-metals (4.73), 30m-indices (not reached by e = 1.0); both methods in each. 30m-metals / 30m-indices were already removed the same day for low trade counts.
**New N:** ICT 29 x 3 = **87**, one-sided confidence 1 - 0.10/87 = **0.998851**; Wyckoff 16 x 3 = **48**, 1 - 0.10/48 = **0.997917**; 6 candidates (3 cells x 2 methods). Cells-file sha256 and `plan_hash` of the commit that made this change are in that commit message (`plan --check-data` prints the sha256, `plan --dry-run` the plan_hash; both change with any later edit to the cells file, the grids or the first-bar data).

**Sensitivity caveats (disclosed, not resolved).**
- The pooling correlation between symbols of a cell is UNVERIFIED; it is the most decision-relevant unmeasured quantity. The primary variant discounts pooled trades for it.
- k = 2 is POST HOC: it was chosen after the earlier ratios (`docs/audits/2026-10-01-power-model.md`) had been seen. k = 1.5 and 2 give the same three cells; k = 2.5 and 3 add 15m-metals, the one cell whose inclusion hinges on k.
- With the undiscounted pooled-rate variant (sum-rate, `sum03` / `rho0` in the audit) 5m-indices (best ratio 1.02-1.25) and 15m-metals (1.80-1.94) would ALSO have passed at k = 2. With a 0.6 discount or the availability-aware metals model the set shrinks. 1m-indices passes in every variant but its margin (1.28) is set by the discount.

**Parked symbols.** UK100 EU50 JP225 HK50 AUS200 US2000 SPN35 N25 (imported for the removed cells) stay in the registry (research-only, except AUS200 which was already registered) and in the data under `data/history`; no data or registry entry was deleted. They are used by no cell; the plan, `plan --check-data` and the readiness gate iterate the declared cells' symbols only, so an unused symbol with missing data or specs is ignored (tested: `test_parked_symbols_are_unused_but_stay_registered_and_nothing_in_the_plan_needs_them`). `FUND_SYMBOLS` (a PINNED constant in `scripts/fund-search.py`, in `FINGERPRINT_FILES`, echoed into the plan as `fund_symbols`) deliberately stays the 17-symbol superset: shrinking it would edit the pinned constant for no behavioural gain, would make a later re-add (below) a second pinned-code change, and `load_cells_file` keeps validating every cell symbol against it. Only a comment above it was updated.

**Contingency (owner).** If the results are unfavourable, option 2 (re-add 15m-metals) or another plan may be considered LATER. That would be a SEPARATE, later pre-registration round (new cells file, new `declare`), and its multiple-testing accounting must include THIS round's comparisons (they would be added to `prior_counts_disclosed`, today `{prop_search_records: 180, diagnosis_slices: 30}` in `scripts/fund-search.py` `PRIOR_COUNTS`: 6 candidates, ICT 87 / Wyckoff 48 comparisons). It is not pre-built: nothing in the code or the cells file anticipates it beyond the `removed_cells` record.

**Pinned files changed by this decision:** `docs/architecture/fund-search-cells.json` (sha256 pinned in the declaration) and `scripts/fund-search.py` (comments / module docstring only; no behaviour). `declare` must run after this change. The tests' six-cell file `scripts/tests/fixtures/fund-search-cells.json` is now a labelled TEST FIXTURE (wide cell list for the late-start, `dev_start` override and shard tests); it is not the plan.

## 2026-10-01 (later): planned-risk admission, zero-risk candidates are refused and counted (coordinator decision, OWNER ACKED 2026-10-02: chat 'Ack')

**Status: coordinator decision; OWNER ACKED 2026-10-02 (chat: 'Ack').**

**Finding.** With the ICT V value `B-EX=fill` the scan produces candidates whose entry equals the stop (e.g. US500 1m 2023-03-07 06:54Z: a flat one-tick-volume bar is the sweep extreme and the first candle of the FVG). `real_costs.cost_r` raises `CostRefused: stop distance is zero`, so a fund-search `run` would abort when it reaches that value set. Only `B-EX=fill` sets produce it (every other value set: zero in every year); Wyckoff cannot (its placement requires entry strictly inside stop/target and `walk()` drops risk <= 0). Counts per cell / symbol / value set / year: `docs/audits/2026-10-01-zero-risk.md`.

**Decision.** A candidate whose planned risk is zero, wrong-side, below one tick (`tick_size` of the real-cost spec) or not a finite price is NOT an order (no position size exists; live would refuse it). It is refused at admission with the counted reason `zero_risk`, per value set and per fold, never priced, never entered, never an R. Pre-registration item 12 (`docs/plans/2026-09-29-fund-search-preregistration-DRAFT.md`). The sub-tick branch is a defensive guard that is not idle but is confined: it refused candidates only in `B-EX=fill` + `B-BUF` value sets (XAGUSD 1m up to 395 in one set, XAUUSD 1m 10, XAUUSD 5m 4; counts in the audit), none in the baseline; only the zero branch is covered by the equivalence evidence (other strict sub-tick cases were one tick plus float noise and are admitted). A sub-tick refusal in the BASELINE would be a method change (none seen). No change to thresholds, grids, cells, min_rr or statistics; `plan_hash` unchanged; trades with a valid stop distance are byte-identical (evidence in the audit).

**Alternative not taken (owner may prefer it):** drop `B-EX=fill` from the grid (changes N and the plan hash) or make the scanner reject the setup (changes the live-shared `ict-scan.py` and hides the count).

**Pinned files changed:** `scripts/backtest-methods.py`, `scripts/real_costs.py`, `scripts/fund-search.py`. `declare` must run after this change.

## Owner decisions 2026-10-02 (red-team review) (owner, in chat; binding; supersedes where it conflicts)
Source: the adversarial review of docs/plans/2026-09-29-fund-search-preregistration-DRAFT.md, accepted by the coordinator, and the owner's decisions of the same day. The full wording is in that draft (sections 0, A and C); this entry records WHAT was decided so it survives a context reset. Nothing here loosens a threshold. Code for the statistics, the report and the engine follows in later steps; the pinning code is in `scripts/fund-search.py` (branch `b21-pinning-text`).

1. **(C5) The window is not pristine.** Data after 2024-03-01 is `oos_exposed` (period `cfd-prop-search-2024-03-2025-03` in `docs/architecture/research-ledger.json`, later dates under ADR 0008); the development window was read for outcomes many times. A development-window PASS is a NOMINATION for a separately pre-registered forward demo, NOT out-of-sample validation. Every prior outcome read is listed with its path in the draft, section 0.1, and `PRIOR_COUNTS` in `scripts/fund-search.py` carries the counts.
2. **(Family A) Multiple testing.** The family is the 6 candidate procedures, with Holm step-down at FWER 0.10 on the primary bound (min of the five bounds = candidate p is the max of the five p-values). Per-candidate floor confidence 1 - 0.10/6 = 0.98333, Holm refines it at report time. This REPLACES the per-method N (ICT 87 / Wyckoff 48; confidences 0.998851 / 0.997917) and the per-grid-value Bonferroni: the nesting already handles value selection. Every other check stays conjunctive.
3. **5m-metals history start by a rule stated before looking.** After the engine fixes, measure admitted-trade counts in the early-fold years; take the EARLIEST of {data start (17 folds), 2009-03-01 (13 folds, XAU + XAG), 2015-01-07 (7 folds, all four symbols)} for which P(every fold >= 30 trades) >= 0.80 for BOTH methods under the availability-aware model; if none qualifies, 2015-01-07. A later step applies it; this entry is the rule.
4. **(I5) Pinning.** The declaration pins the git tree hashes of `scripts/`, `docs/architecture/` (without `research-ledger.json`, which holds the declaration), `data/history/costs/ftmo` and `data/history/ftmo`, the repo HEAD sha, the extended per-file fingerprint list, and the Python version and platform (a different Python is a NOTE, not a refusal: CI 3.12, owner's machine 3.14). `declare`, `run` and `scan` refuse a modified or untracked file under `scripts/`, `docs/architecture/`, `data/history/` (not `config/`, `.claude/`); `--allow-dirty` for tests and dry runs only. The same stamp is in the scan-cache stamp.
5. **(I6) Deployment rule.** The SAME selection rule re-run on the training data through 2024-03-01 (not 'the values chosen in the final fold'); several passes: the highest bound at the common level first; every pass goes to a separately pre-registered forward demo (deployed configuration, news filter ON, measured commission, its own length and trade target). Deployable-spec differences from live are listed in draft item 11.
6. **(I7) Report obligations, definitions sealed now:** minimum detectable edge, upper confidence bound at 0.98333, every failed check with its margin, fold-by-fold mean net R and mean spread_R, stability of chosen values, placebo benchmark, 1m-metals / 5m-metals overlap statement, scope statement (draft section C).
7. **(I8) Open items closed.** O3 keep 365/730 fold sizes. O4 per 5. O5 the allow-list stays. O6 commission unknown: stress margin 0.003 % of notional per round turn, a stress margin and NOT an estimate; the owner may measure FTMO's commission with a demo round trip later and the report restates it. O7 regime = D1 ADX(14) of the last completed D1 bar at or before entry, median split of pooled TEST trades. O8 the earlier text was stale: `walk()` already flattens a fill on the last bar of a server day (commit 2869c35); the document and `ROLLOVER_EDGE_NOTE` now say so, no engine key is added.
8. **Perturbation, stress and prop-shift definitions.** Perturbation = ORDINAL components only, one at a time (ICT: B-BUF 0 < 0.1 ATR < 0.25 ATR; B-EX iofed < ce < fill; B-EXIT target -2.0 < -2.25 < -2.5 and time stop H < 1.5H < 2H < none; B-LB lookback 8 < 12 < 16 and expiry K < 2K. Wyckoff: W6 300 < 600; W-TW window 8 < 12 < 20 and swings 2 < 3; W4a only between the explicit counts 3 and 4, not perturbed when a fold chose the v1-typed baseline), gated on the neighbour's pooled mean > 0 AND neighbour robust bound > 0 at 1 - 0.10/6; categorical flips are reported, not gated. Stress gate: a PASS also needs pooled mean net R > 0 under the p90 spread (price-scaled) on both legs plus the 0.003 % commission margin on the same admitted trades; prop_pass must also be >= 0.70 with R shifted down by (mean - bound at 0.98333) [SUPERSEDED 2026-10-02 'final decisions': the shifted prop pass is REPORT-ONLY, not a condition].
9. **Ledger.** XPTUSD and XPDUSD were added to the instrument list of the development period `cfd-development-pre-2024-03` in `docs/architecture/research-ledger.json` (the 5m-metals cell reads them). No `fund_search` declaration was written.

**Pinned files changed by this decision:** `scripts/fund-search.py` (FINGERPRINT_FILES, pinning, `PRIOR_COUNTS`, `ROLLOVER_EDGE_NOTE`; `plan_hash` unchanged), and, under the new `scripts/` tree pin, `scripts/tests/test_fund_search.py`. `docs/architecture/research-ledger.json` (the instrument list) is NOT pinned: the ledger is excluded from the docs/architecture tree pin by design. `declare` must run after this change.


## 2026-10-02: engine realism before `declare` (coordinator decision from the red-team review, disclosed to the owner in chat and covered by the owner's authorisation to declare after red-team alignment (2026-10-02))

**Status: coordinator decision (red-team review); disclosed to the owner in chat and covered by the owner's authorisation to declare after red-team alignment (2026-10-02).** Pre-registration item 13
(`docs/plans/2026-09-29-fund-search-preregistration-DRAFT.md`) is the sealed text; item 9 (cost model) is amended. Nothing was
evaluated: no R, expectancy or win rate was computed for any of this; only counts and equivalence hashes.

**Findings (an expert red-team review; each confirmed by reading the code).**
1. **C1 (harness bug).** `BtEngine.trades_for` passed the overlay to `bt.scan(opts=...)` but `bt.simulate()` reads the module-global
   `OPTS`, so the harness ran the v1 exit-hour min_rr admission although O1 (owner 2026-09-30) is ON in every cell and the
   record said so. Fixed: every harness simulate runs under `dict(bt._OPTS_BASE, **fixed_opts())` (restored exception-safe); the
   simulate-time OPTS reads are audited and pinned (`min_rr`, `fx_admission_entry_cost`, the `floor` token of `fx_b_exit`;
   `mgmt` is read by `walk()`, not `simulate()`); `prop_pass` uses the fixed set only; a V key that became simulate-time is refused.
   Consequence for the owner: O1 as decided is now what the harness does. Under the old code the declared record text was wrong.
2. **C2 (absolute spread at today's prices).** New cost profile `ftmo_demo_2026_09_relspread` (spread scaled by `entry /
   price_ref`, `price_ref` = median M15 close over exactly the spreads' recording window). The old absolute profile is
   byte-identical and stays selectable as the reported sensitivity. The declaration pins the profile, the `price_ref` values and
   a provenance hash. Measured price ratios (not R) are in item 13(b): the old profile overstated gold's spread by ~1.5-2x for
   most folds and up to 6x in 2004; it UNDERstated palladium's in 2020-2022.
3. **C3 (no gap slippage).** `walk()` filled a stop at the stop price even when a bar opened beyond it. New fixed key
   `fx_gap_fill` (default False = v1; ON in every fund cell; live never sets it): a stop (also a breakeven stop) fills at the worse of
   the stop and the bar open when the open is beyond the stop; targets and limit entries fill at their own price (no improvement);
   a same-bar fill-and-stop obeys the same rule; `R_planned` and min_rr admission are unchanged. v1 (key off) is byte-identical.

**Owner questions this raises (not decided here).** (i) Accept `fx_gap_fill` and `ftmo_demo_2026_09_relspread` as fixed rules of
the evaluation baseline (they make the backtest less optimistic about costs and fills; neither changes a threshold, grid, cell,
min_rr or statistic). (ii) A trade stopped by a gap now has `R < -1`; the 1%-risk sizing is unchanged, so a gap loss exceeds the
planned risk, as it would live. (iii) The relative profile also RAISES a cost where the symbol traded above its reference price
(palladium 2020-2022); that is intended (the spread is a fraction of price) but is a different sign from the gold case.

**Evidence (counts and hashes; see item 13 for the figures).** see pre-registration item 13 (`Evidence`) and `docs/audits/2026-10-02-engine-realism-census.md`.

**Pinned files changed (declare must run AFTER):** `scripts/backtest-methods.py`, `scripts/real_costs.py`,
`scripts/fund-search.py`, `scripts/scan_many.py` (all in or beside `FINGERPRINT_FILES`), `docs/experiments/fund-search/plan.json`
(the plan core gained `cost_profile_pin`, `adopted_f_keys` gained `fx_gap_fill`, `cost_profile` changed; `plan_hash`
4a476bee674afcbb -> 5476f042bdde09f1). Also touched, not pinned: `scripts/snapshot.py`, `scripts/stability-report.py` (`fx_gap_fill` registered),
`scripts/diagnose-methods.py` (the two `walk` wrappers forward `**kw`). The cells file, grids, thresholds and `min_rr` are untouched.


## 2026-10-02: implementation of the sealed statistics (branch `b20-stats-sealed`; coordinator-dispatched implementation, disclosed to the owner in chat and covered by the owner's authorisation to declare after red-team alignment (2026-10-02))

**Status: implementation of decisions already taken (owner + coordinator + red team, entry "Owner decisions 2026-10-02" above).** No threshold,
grid, cell or `min_rr` changed; no engine, cost or walk change (those are the merged b19). Nothing was evaluated: no R, expectancy or win rate
of real data was read (synthetic trades, hand-seeded raw trades on a temp slice, and counts of D1 label hours / gaps only). The text is the
SPEC (pre-registration draft, sections 0.2, A2, A5, A7, A8, A11, C); where it was ambiguous the most conservative reading was implemented and is
listed here.

**What the code now does** (`scripts/fund_stats.py`, `scripts/fund-search.py`; the draft's "Implemented" paragraphs say how):
1. **Family A.** The multiple-testing family is the candidate procedures (declared cells x methods = 3 x 2 = 6; counted on the DECLARED cells, so a
   cell dropped for lack of data still counts). Per-candidate primary bound = min of the five bounds; `p_robust` = max of the five one-sided p-values
   (bound > 0 at c <=> p_robust < 1 - c, tested); floor confidence 1 - 0.10/6 = 0.98333 for every candidate (replaces N 87 / 48 and the per-grid-value
   Bonferroni; grid values stay disclosed: ICT 29, Wyckoff 16 per cell). Plan core `family`, declaration `family_size` / `floor_confidence` /
   `family_members` / `family_rule` (replacing `n_by_method` / `confidence_by_method`; `cell_count` unchanged), `plan --dry-run`, record `primary`
   (five bounds, five p-values, `p_robust`, floor verdict, half-year se / df) and `report` (Holm over the six PLANNED candidates; NOT RUN, insufficient
   and not-computable ones enter with p = 1).
2. **Perturbation.** Ordinal components only, one at a time, from the constant `PERTURBATION_AXES` in `fund_stats.py` (pinned in the plan core and in
   `evaluation_config.perturbation`); gate = neighbour pooled mean > 0 AND primary bound > 0 at the floor; categorical items flipped and reported;
   W4a baseline-typed folds listed under "Not perturbed". The table is tested against the real grids.
3. **Regime.** D1 ADX(14) (Wilder) of the last D1 bar whose close is at or before the entry; the decision-timeframe ADX stays on the trade as `adx14`
   for reporting only. The D1 series' identity is in the record's `dataset_snapshot.regime_series`.
4. **Stress gate and shifted prop pass (the shifted pass was later demoted to REPORT-ONLY: see 'final decisions 2026-10-02').** `BtEngine.stress_trades` (p90 spread both legs, price-scaled, + 0.00003 * entry / |entry - stop| R, same admitted
   trades) gated on the mean > 0, the stressed bound reported; `BtEngine.prop_pass(pooled, r_shift)` with the shift = mean - primary bound subtracted from
   every admitted trade's net R after `simulate()`. `scripts/performance.py` and `scripts/prop-search.py` are NOT modified (the shift lives in the
   harness), so prop-search is unchanged by construction. An engine without stress pricing, and a bound that cannot be computed, fail closed.
5. **Report (section C, cheap items).** Minimum detectable edge and upper bound at 0.98333 from the binding half-year CR1 se / df (and for the numerically
   smallest bound when it differs), every check with its margin, fold-by-fold mean net R and mean spread_R, stability of the chosen values per item and
   per ordinal component, the overlap / scope / window statements, "placebo: NOT IMPLEMENTED in this build" and the git sha of the build.
6. **Verdict.** `insufficient` still overrides; `verdict_from` needs every check in `REQUIRED_CHECKS` and FAILS CLOSED when a stored record lacks one;
   `VERDICT_PRECEDENCE`, `FAMILY_DEFINITION`, `REGIME_SPLIT_DEFINITION`, `PERTURBATION_DEFINITION`, `STRESS_DEFINITION`, `PROP_SHIFT_DEFINITION` are pinned
   in `evaluation_config`. The stale `last_bar_entry_times` docstring (O8) is corrected.

**Where the text was ambiguous (owner / coordinator to confirm):**
- **Holm vs the floor.** The brief said a candidate that fails the floor can never be Holm-rejected. That is not true of Holm: rank 1's threshold equals the
  floor (0.10/6) but ranks 2..6 are looser (0.10/5 ... 0.10), so a candidate with p between 0.0167 and 0.02 that ranks second IS Holm-rejected while failing
  the floor (unit-tested). The draft's A2 also said "a candidate's check passes iff Holm rejects it". Implemented, conservatively: the verdict is the
  conjunction of every check including the floor test; Holm only confirms (a floor pass is always Holm-rejected); a Holm-only rejection is listed in the
  report as "Holm would reject, but the floor fails (NOT a pass)". If the owner wants Holm's looser ranks to count, that is a LOOSENING and a ledger event.
- **D1 "completed bar".** The repo convention is verified (D1 `time` = open label in UTC, server midnight; `normalized.available_time` = open + 1 bar). The
  close used is max(open + 24 h, next D1 open): equal to the brief's open + 1 day except on 25 h DST days (where open + 24 h would be an hour early) and across
  gaps, where it only reads an older bar. Stricter only.
- **Family size** is counted on the declared cells (6), not on the cells that survive the data gate (the old N shrank with them).
- **Insufficient candidates** enter Holm with p = 1 (their p is reported, not used).
- **Shard layout.** `WAVE2_SETS_PER_FOLD` (11.25 / 7.75) was measured under the old perturbation definition; wave 2 now also holds the ordinal neighbours and the
  categorical flips. It only sizes Actions jobs, never a result, but must be re-measured (`scripts/research/shard_calibration.py`, which now also requests the
  flips) before the real run is laid out.

**Pinned files changed (declare must run AFTER):** `scripts/fund_stats.py`, `scripts/fund-search.py`, `scripts/research/shard_calibration.py` and the tests under the
`scripts/` tree pin (`scripts/tests/test_fund_search.py`, `test_simulate_time_opts.py`, `test_speed_equivalence.py`, `test_min_rr_floor_25.py`);
`docs/experiments/fund-search/plan.json` (plan core: `family` and `perturbation_axes` replace `n_by_method`, candidates carry `family_size` /
`floor_confidence`, constants gained the stress and MDE constants; `plan_hash` 5476f042bdde09f1 -> a043358b89314982). `scripts/performance.py`,
`scripts/prop-search.py`, `scripts/backtest-methods.py`, `scripts/real_costs.py`, the grids, the cells file and `min_rr` are untouched.

## dev_start decisions by availability rule (2026-10-02)

Rule: draft section 0.3 (owner approved 2026-10-02 for `5m-metals`): per cell, the EARLIEST candidate start with P(every test fold >= 30 admitted trades) >= 0.80 for BOTH methods under the availability-aware model (cell-selection T3-avail; rho 0.3; fixed seeds; 2000 replications), else the last candidate. Inputs: admitted-trade counts per symbol-year (harness engine as merged) and bar counts only; no outcome figure was read. Full numbers: `docs/audits/2026-10-02-dev-start-decision.md`.

**Disclosure of the extension.** The owner approved the rule for `5m-metals`. The coordinator extended the SAME principle to `1m-indices` after the engine census (`docs/audits/2026-10-02-engine-realism-census.md`) showed sparse 1m index data before 2021, and added the condition that every test fold needs at least ceil(2m/3) = 4 of 5 symbols with dense data (>= 50 % of expected bars) in the fold or its preceding training window. Both were fixed before any count was read and before any outcome was seen. The owner may overrule the extension (1m-indices then reverts to `dev_start` null, 4 folds, and `plan_hash` changes again).

| cell | candidate | folds | P ICT | P Wyckoff | dense condition | verdict |
|---|---|---|---|---|---|---|
| 5m-metals | 2004-06-11 | 17 | 0.562 | 0.101 | n/a | fails |
| 5m-metals | 2009-03-01 | 13 | 0.735 | 0.905 | n/a | fails (ICT < 0.80) |
| 5m-metals | **2015-01-07** | 7 | 0.994 | 1.000 | n/a | **chosen** |
| 1m-indices | 2017-12-27 | 4 | 1.000 | 1.000 | FAIL (fold 1, 2020-03..2021-03: only US30 dense) | fails |
| 1m-indices | **2020-03-01** | 2 | 1.000 | 1.000 | PASS (5 of 5 dense in both folds) | **chosen** |

Open point for the owner: the 5m-metals verdict depends on the discount convention of the availability model. Primary (T3-avail, the cell's full k in the rho-0.3 discount) is what the rule names and is what was applied. A sensitivity (discount over only the symbols that have trades in the fold) gives 2009-03-01 P 0.923 (ICT) / 0.980 (Wyckoff), i.e. it would pass and win (13 folds); 2004-06-11 still fails (0.892 / 0.559).

Applied: `docs/architecture/fund-search-cells.json` (1m-indices 2020-03-01T00:00:00Z, 5m-metals 2015-01-07T00:00:00Z; `1m-metals` null), `scripts/research/span_equivalence.py` re-run for both cells (sha256 identical, full vs cut, both methods; section 3 of the audit), `docs/experiments/fund-search/plan.json` recommitted (no ledger declaration exists): `plan_hash` a043358b89314982 -> 12331b40583a6bd3. Folds now: 1m-metals 9, 1m-indices 2, 5m-metals 7. The real-plan shard layout (test pin) is now 288 shards (62 wave 1 + 226 wave 2; was 289 = 62 + 227); `shard_calibration.py` should be re-measured before the real run is laid out (as already noted 2026-10-02).

**Pinned files changed:** `docs/architecture/fund-search-cells.json` (hashed into `plan_hash`), `docs/experiments/fund-search/plan.json`, `scripts/research/trade_rates.py`, `scripts/research/dev_start_decision.py` (new), `scripts/tests/test_fund_search.py` (scripts/ tree pin). `declare` must run AFTER this change and after the owner's ack.

## 2026-10-02: review fix round 1 before the fund-search `declare` (branch `b26-review-fixes`; coordinator decisions, disclosed to the owner in chat and covered by the owner's authorisation to declare after red-team alignment (2026-10-02))

**Status: fixes to the merged engine-realism and statistics work; no threshold loosened, no cell, grid, cost, spread or `min_rr` change; nothing evaluated (no R, expectancy or win rate of real data read).**

- **Regime split balance rule (TIGHTENING; OWNER ACKED 2026-10-02, chat 'Ack').** Each D1-ADX half must hold at least 25 % of the pooled TEST trades, else the regime check FAILS with
  'regime halves unbalanced'. Reason: ties at the median (many trades share one symbol-day D1 ADX) could leave a tiny half that still passed (ADX [10, 20, 20, 20, 50],
  all +0.5 R: low 4 / high 1, `ok`). Documented in the draft item 7 and pinned in `REGIME_SPLIT_DEFINITION` (so `evaluation_config.regime_split` carries it). Only ever fails
  more candidates; allowed before sealing.
- **Holm never loosens the verdict** is now guarded by a test of `verdict_from` (only `lower_bound_positive` failing is a FAIL) and by a `cmd_report` test (a candidate Holm
  rejects at rank 2 while it fails the floor is not in the passes and is listed under "would reject, but the floor fails (NOT a pass)"); mutation-checked.
- **Fail-closed robustness.** `verdict_from` treats a missing `folds_sufficient` as not sufficient (no KeyError); `stress_commission_r` / `stressed_net_r` return None when not
  computable and the stress gate FAILS on it (unreachable today because of the zero-risk refusal; the guard stays); `build_cells` REFUSES a declared `dev_start` that yields
  fewer than `MIN_TEST_FOLDS` (2) folds.
- **Dirty-tree check.** `scoped_dirty()` ignores a `*.lock` file only when `git check-ignore` says the repo's own `.gitignore` ignores it (so the 0-byte, gitignored
  `docs/architecture/automation-config.json.lock` does not make `declare` refuse), and it now ALSO refuses a tracked file under the scoped paths that carries the
  skip-worktree or assume-unchanged flag.
- **Same-bar fill-and-stop in COMBINED-BOOK obeys the gap rule (13c)** now has its own hand-built-bar test (mutation-checked); engine behaviour unchanged.
- **Disclosures.** `price_ref`: XPTUSD / XPDUSD have 99,999 bars in the spec window (spec 100,000; last bar 02:45 UTC missing; the other seven symbols match; median effect nil), and
  `price_ref` reads closes up to 2026-09 / 10, after the development cutoff, as a constant cost-calibration scale (not an outcome read); added to the draft item 9. Comments and
  docstrings aligned with the facts (draft 13b: 1.5-2.1x spread overstatement for most gold / silver folds; ICT N = 29; B-EXIT = 12 value sets; fold counts 9 / 2 / 7;
  the D1 label convention is `us_dst_dates_fixed_offset`).
- **Plan test.** `docs/experiments/fund-search/plan.json` `plan_hash` is now tested against `build_plan()` on the real cells file, grids and data, so a stale committed plan fails a test.

**Pinned files changed (declare must run AFTER):** `scripts/fund_stats.py`, `scripts/fund-search.py`, `scripts/real_costs.py` (docstring only), the tests under the `scripts/` tree pin,
`docs/experiments/fund-search/plan.json` (recommitted at the end of this branch).

## 2026-10-02: FTMO minimum trading days becomes an explicit prop-gate check (branch `b27-min-trading-days`; owner confirmed 2026-10-02 in chat; a tightening)

- **Decision (owner, 2026-10-02):** FTMO requires at least 4 trading days, as recorded in the repo profile `ftmo-challenge-phase1` (`min_trading_days: 4`, still flagged for
  verification: 2024+ sources report 4, older sources 10). The owner confirmed adding an EXPLICIT check to the prop gate: a tightening, harmless in practice because every fold needs
  >= 30 trades in 365 days.
- **Definition (draft item 8c, pinned as `FS.MIN_TRADING_DAYS_DEFINITION` and `evaluation_config.min_trading_days`):** per test fold, the number of distinct UTC ENTRY days among the
  pooled test trades must be >= the profile's `min_trading_days`, for every prop-gate fund that declares one (FTMO: 4); The5ers (no field) is not checked; an unreadable profile fails
  the check. A necessary-condition proxy (365-day fold vs the 120-resampled-day challenge horizon), not a replay. Required for a PASS, fails closed when absent from a record.
- **Not touched:** `scripts/performance.py`, `scripts/prop-search.py`, the engine, cells, grids. The plan core is unchanged (plan_hash 275763cb81b0518a).
- **Pinned files changed (declare must run AFTER):** `scripts/fund_stats.py`, `scripts/fund-search.py`, the tests under the `scripts/` tree pin, `scripts/research/e2e_power.py`
  (check added to the simulator; not a verdict input of the harness).

## 2026-10-02: report-only obligations implemented before `declare` (branch `b28-report-obligations`; coordinator-dispatched, disclosed to the owner in chat and covered by the owner's authorisation to declare after red-team alignment (2026-10-02))

**Status: the placebo benchmark, the per-year / fold table and the data disclosure of draft section C are IMPLEMENTED, not only specified (owner/red-team instruction: before results are read). Report-only: no verdict, check, margin, threshold, Holm step, grid, cell or engine behaviour changed; nothing evaluated (synthetic tests only; the only real-data read is first-bar labels and the export bar count).**

- **Placebo (draft section C item 6).** Per candidate, computed at run time inside `evaluate_with_engine` (`attach_report_only`, after `evaluate_cell`) by `BtEngine.placebo_trades`: one random entry per real pooled TEST trade, same symbol, fold and UTC hour-of-day, side 50/50, same stop distance and `R_planned`, run through the engine's own `walk()` and `real_costs.cost_r` and the same planned-risk / `min_rr` admission. Pinned seed `fund-search-placebo-v1`, derived per real trade (order-independent). Report: placebo pooled mean net R, real minus placebo, 95 % percentile bootstrap over the test folds, skipped placebos counted by reason. Labelled "REPORT-ONLY: a PASS requires nothing from this". The "placebo: NOT IMPLEMENTED in this build" line is gone; the build sha is printed in the header and the statements. Definition and the open choices (entry = bar open and walk from the next bar, no redraw, one-position rule not applied, bootstrap rough with few folds) are in the draft, section C "Implemented" paragraph and `FS.PLACEBO_DEFINITION`.
- **Per-year / fold table.** New record key `metrics.evaluation.fold_year_report` (existing `fold_cost_report` untouched): per test fold trades, mean net R, mean `spread_R`, mean net R under the stress re-pricing, share of entries per UTC hour bucket (4), cost regime ratio (mean of `spread_R / R_planned`).
- **Data disclosure in the report header.** First bar of every stored series (from its `index.json`), export bar count, bars scanned, each cell's development start and earliest symbol; the 1m-metals 5,000,000-bar export cap with BOTH metals' first bars (read from the store: XAUUSD 2012-06-14T17:46:00Z, XAGUSD 2012-05-03T05:38:00Z, not the 2012-05 for both that was assumed); the sparse-data note for the 1m indices from `docs/audits/2026-10-02-dev-start-density.json`.
- **Not in the plan core:** `plan --dry-run` `plan_hash` stays `275763cb81b0518a` (checked before and after). New record keys are additive; the placebo and table are computed after the evaluation and are not read by `verdict_from`.
- **Tests:** `scripts/tests/test_fund_search_report_obligations.py` (placebo construction, determinism and order independence, zero-edge placebo close to real, planted edge beats it, per-year values, disclosure vs the stored series, verdict unchanged on / off / better / failing; mutation-checked: hour filter and side draw), `test_fund_search.py` report test updated for the removed line.

**Pinned files changed (declare must run AFTER):** `scripts/fund_stats.py`, `scripts/fund-search.py`, the tests under the `scripts/` tree pin. `docs/experiments/fund-search/plan.json` is unchanged (plan core not touched).

## 2026-10-02: final decisions (branch `b29-final-decisions`; owner, in chat, binding; applied before `declare`)

- **(A) The SHIFTED prop pass is REPORT-ONLY.** It leaves the verdict conjunction and `REQUIRED_CHECKS` (now nine); it is still computed, recorded (`metrics.evaluation.report_only.prop_pass_shifted`) and printed in the report as 'REPORT-ONLY' with the shift and the values. No threshold changed; the shift definition (pooled mean - primary bound at 0.98333) is unchanged. The verdict keeps: floor bound, insufficient guard, stability, frequency, D1-ADX regime split (>= 25 % half guard), ordinal perturbation, stress mean > 0, the UNSHIFTED prop pass >= 0.70 for every fund, min_trading_days (FTMO 4). `verdict_from` evaluates exactly `REQUIRED_CHECKS`: a record lacking the shifted check still passes the logic; one lacking the unshifted prop check fails closed. `VERDICT_PRECEDENCE` and `PROP_SHIFT_DEFINITION` (pinned in `evaluation_config`) now say so.
  - **Reason and numbers.** The shifted pass was the check that cost the power (it asks the bound, not the mean, to reach e*). Whole-conjunction e80 before -> after: 0.25 / 0.25 / 0.40 / 0.40 / 0.30 / 0.30 -> 0.20 / 0.20 / 0.30 / 0.30 / 0.30 / 0.25; P(PASS) at own e* 0.16 / 0.02 / 0.12 / 0.04 / 0 / 0 -> 0.77 / 0.23 / 0.80 / 0.52 / 0 / 0; expected number passing at own e* 0.34 -> **2.31**; type I 0/3000 everywhere (Wilson 0.0009). Inclusion rule unchanged (1m-metals 0.66, 1m-indices 0.96, 5m-metals 1.62: all INCLUDED at k = 2). Source: docs/audits/2026-10-02-e2e-power.md section 9; superseded: the figures 0.27 / 0.34 of sections 1 and 8.
- **(B) Two later stages pre-registered as sealed text (draft section 0.5).** (i) EXPOSED-WINDOW REPLAY before any forward demo: each nominated (PASS) configuration (the deployment rule: the same selection re-run on training through 2024-03-01) is replayed on the exposed window 2024-03-01 -> latest data, labelled exposed per plan section 4 (historical windows are disclosed, exposed checks, not validation); gate: pooled mean net R > 0 under the same costs and fills; the unshifted prop_pass reported (>= 0.70 desired, not a gate), the per-year table and the placebo reported; a failure ends the nomination. (ii) FORWARD DEMO outline: a separately pre-registered demo whose primary purpose is a paired execution comparison (per live signal: realised fill, slippage, spread, commission vs the backtest replay of the SAME signal, i.e. implementation shortfall per trade) plus mean R > 0; its own length and trade target are stated in that later pre-registration; it cannot confirm a 0.70 pass probability within months.
- **(C) DISCLOSURES (draft section 0.6):** the 1m export cap (5,000,000 bars; XAUUSD first 1m bar 2012-06-14T17:46Z, XAGUSD 2012-05-03T05:38Z, so the earliest 1m-metals folds are partly one-symbol); the F-item adoption with outcomes visible; 1m-indices SHORT SPAN (test 2022-03..2024-03, 2 folds, one bear and one bull year: 'a PASS says 2022-24 behaviour', printed by the report on every 1m-indices PASS, report-only text); dependence between 1m-metals and 5m-metals; the e2e model's limits (binary outcomes, no selection simulated, tau unmeasured); the commission margin is a stress allowance, not an estimate; FTMO min trading days = 4 flagged for verification; no news filter in the search; ask-side triggers not modelled.
- **Not touched:** thresholds, engine, cells, grids, `scripts/performance.py`, `scripts/prop-search.py`. Plan core unchanged (plan_hash 275763cb81b0518a, checked). The e2e raw results `docs/audits/2026-10-02-e2e-power-final.json` are new.
- **Pinned files changed (declare must run AFTER):** `scripts/fund_stats.py`, `scripts/fund-search.py`, the tests under the `scripts/` tree pin, `scripts/research/e2e_power.py` (simulator only). `docs/experiments/fund-search/plan.json` unchanged.
- **Flag for the owner:** the expected number of passes at own e* moved from 0.34 to 2.31 and the 1m cells' e80/e* fell to 1.0-1.5; no cell stops satisfying the inclusion rule, the cells file was not edited. 5m-metals still needs 2.6-3.3 x its e* (perturbation binds).

## 2026-10-02 (after declare): strategic diagnosis and new direction (owner, in chat; binding)

Full record: `docs/audits/2026-10-02-strategic-diagnosis.md` (read §0 and §6 first).
1. **Goal:** pass FTMO with ANY validated method; ICT/Wyckoff are one hypothesis family, not the required edge source.
2. **Fix defects #3 (FVG self-touch in the "already triggered" gate, backtest and live), #4 (prop-pass horizon counts
   trade-days, not weekdays) and #5 (prop simulation risk fixed at the 1 % ceiling), then RE-DECLARE the fund-search.**
   The current declaration (`c4ea722`, plan_hash `275763cb81b0518a`) must not be run; no fund-search record exists yet.
   The re-declaration must add the development-window reads listed in the diagnosis §7 to the prior-reads table.
3. **Forward demo is the primary evidence**; a looser, pre-registered nomination gate to demo is accepted; the strict
   gate applies to real money only.

**Applied 2026-10-02 (same session):** D3/D4/D5 implemented and tested; power re-run (`docs/audits/2026-10-02-e2e-power.md`
§10); re-declared with `declare --supersede` (plan_hash 275763cb81b0518a -> 0ec4e27e15fa7df9, no record existed; the old
declaration is kept in `research-ledger.json` `fund_search_superseded`). Pre-registration section 0.7 records the change.

## 2026-10-02 (later): forward stage, book design and demo orders (owner, in chat; binding)

- Historical data cannot confirm the F2 survivors (every year was read to select them); confirmation stays forward
  (docs/plans/2026-10-02-edge-followup-preregistration.md §4). The full history is used for DESIGN only
  (docs/audits/2026-10-02-fvg-book-sim.md).
- **Demo order wiring APPROVED** ("Đồng ý duyệt nối demo order"): `scripts/fvg_demo.py`, DEMO only, `enabled=false` until the
  owner switches it on (docs/architecture/fvg-demo.json). Real money is out of scope.
- A broader pre-registered hypothesis family (daily horizons, mean reversion after large moves, volatility-regime filter) is
  approved as the next research step.
- Note for the fund-search: research scripts added after its re-declaration changed the `scripts/` tree pin, so
  `fund-search.py run` now refuses on drift; running it needs a re-declaration (no record exists) or `--allow-drift`.
