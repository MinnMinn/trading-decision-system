# Symbol universe: full FTMO CFDs and FTMO crypto CFDs (design, 2026-10-01)

Update 2026-10-01 (branch b15-fund-symbols): the owner chose a much smaller universe than this design considered (no FX, crypto, energies or stocks): see `docs/plans/2026-09-30-owner-decisions.md`, section 'Owner decisions 2026-10-01 (symbol universe)'. The registry holds nine research-only symbols (`research_only.cfd`), the fund search kept its 6 cells (N 174 / 96) with per-cell symbol lists at that time (later the same day reduced to 3 cells, N 87 / 48; the eight index symbols are parked: see the owner-decisions section 'cell selection: three cells'), and `fund-search.py plan --check-data` reports missing history/specs. Section A.0's side effects are handled there (the live surfaces, the SessionStart hook, `/analyze` and `trading_system.py` read `live_analysis`, i.e. analysis minus research-only); sections A.2 and B below describe the options as designed (new classes, extra cells) and are kept as history.

Status: **design only.** No pinned file changed (`scripts/fund-search.py`, `FUND_SYMBOLS`, `docs/architecture/instruments.json`,
grids, ledger). Owner decision 2026-10-01: add the "full" FTMO CFD universe and FTMO crypto CFDs to raise statistical power.
What exists on this branch is the pipeline that prepares for it without MT5 or new data:
`integrations/mt5/ExportSymbolList.mq5`, batch mode in `integrations/mt5/ExportHistory.mq5` (v1.01), `scripts/import-ftmo-symbols.py`
and `docs/architecture/mt5-ftmo-symbol-universe-export.md`. **The MQL5 is UNTESTED** (never compiled).

Today: 7 FTMO symbols have history (XAUUSD, XAGUSD; US500, US30, USTEC, DE40, FRA40), AUS200 has a cost spec only
(`docs/audits/2026-09-29-ftmo-history-coverage.md`). The fund search ran 6 cells = {1m, 5m, 15m} x {metals, indices} when this was written; since 2026-10-01 it declares 3 (1m-metals, 1m-indices, 5m-metals).

The local Binance USDT history (`data/history/ohlcv.*USDT.*`) is Binance **spot**: different costs, different hours. It is not an
FTMO crypto CFD and must not stand in for one in any fund search or cost estimate.

## A. What the harness needs

### A.0 The registry comes first, and it is not free (measured)

`scripts/import-mt5-history.py` refuses a symbol that is not on the instrument allowlist (`scripts/import-mt5-history.py:136`) and
`scripts/instruments.py` raises for any symbol on no analysis list (`is_continuous`, `data_dir`, `is_tick_volume`). So every new symbol must be on
`analysis.cfd` before its history can be imported. That list is read by more than the research code. I applied the importer's
proposal for 6 symbols (EURUSD, GBPUSD, USDJPY, USOIL, BTCUSD, ETHUSD) to a **copy** of the repo and ran the affected tests:

| Effect | Evidence (copy of this tree, 2026-10-01) |
|---|---|
| `prop-search.py` candidate space 180 -> **342**, silently | `build_candidate_space()` iterates `analysis("cfd")` (`scripts/prop-search.py:113`, `:122`); fund-search `PRIOR_COUNTS["prop_search_records"]` is 180 (`scripts/fund-search.py:103`). `test_prop_search` still passes (82 tests): nothing guards it |
| live page lists each new symbol as "no feed" | `STYLE_SYMS` over `I.analysis(m)` (`scripts/build-artifact.py:125`); `test_build_artifact` 1 new failure (`NoSymbolIsDroppedSilently`), 88 tests pass on the unpatched copy |
| re-adding forex majors trips the 2026-09-27 removal guards | `test_instruments_sync` `ForexWasRemovedCleanly` (2 new failures) |
| derived schema enums drift | `scripts/sync-instruments.py --write` fixes it (`test_derived_schema_enums_in_sync`) |

Pre-existing and not caused by this work: `test_instruments_sync.test_no_script_hardcodes_the_mt5_symbol_set_or_the_feed_directories`
already fails at 6e14cc2 (it flags `scripts/fund-search.py:66`, i.e. `FUND_SYMBOLS`, and `scripts/diagnose-methods.py:42`).

Consequence: a research-only symbol list is missing from the registry. Either (a) accept the side effects and fix prop-search by
pinning it to an explicit symbol list, or (b) add a registry notion of "research universe" that live scanning, the page and
prop-search ignore. That is a TechLead/owner decision; this task does not make it. `import-ftmo-symbols.py` proposes only the
minimum (`canonical`, `display`, `analysis.cfd`), never `execution` or `backtested`, and prints these side effects.

### A.1 How a cell is built today

A cell is `<timeframe>-<asset_class>`. Symbols of a class are those of the **pinned** `FUND_SYMBOLS` whose registry
`display(sym)["asset_class"]` equals the class (`scripts/fund-search.py:66`, `:68`, `build_cells` at `:226`). On branch
`b11-cell-spans` (read only) the cells are declared in `docs/architecture/fund-search-cells.json` and `load_cells_file` refuses a
cell whose class is not in `ASSET_CLASSES`, whose symbol is not in `FUND_SYMBOLS` or has another `asset_class`, whose id is not
`<tf>-<class>`, or that lacks a `rationale`/`decision` string; that file is hashed into the plan and pinned in the declaration.
`N = (N per cell) x (cells)` per method (`scripts/fund-search.py:272`); a cell with no symbol with history before the
development cutoff is excluded from N by data availability only.

### A.2 New cells per class

| Class | Cells | Symbols | Specific issues |
|---|---|---|---|
| `fx` | `1m-fx`, `5m-fx`, `15m-fx` | the importer's Forex list (path head `Forex`) | ICT B7 killzone is indices-only, so for FX it is inert (below); no sourced FX session window for this project (`docs/architecture/session-model.md` header: the ICT sources do not settle forex vs index windows); swap mode and commission unknown until the spec export |
| `energies` | `1m-energies`, `5m-energies`, `15m-energies` | path head `Energies` (how many FTMO lists is unknown until ExportSymbolList runs) | few symbols per class means a small `m`; same cost questions |
| `crypto` | `1m-crypto`, `5m-crypto`, `15m-crypto` | path head `Crypto` (FTMO crypto CFDs only) | hours, weekend gaps, fees, name clash with the Binance class (below) |
| `other` | none | stocks, ETFs, anything unmapped | a heterogeneous bucket is not a coherent cell; the importer lists unmapped path heads with counts and excludes them. A class is added only when the owner names it and accepts its 3 cells of N |

### A.3 Exact code points (file:line at 6e14cc2; branch names where the code is not on this tree)

| # | Where | What must change | Pinned (`FINGERPRINT_FILES`) |
|---|---|---|---|
| 1 | `scripts/fund-search.py:66` `FUND_SYMBOLS` | add the chosen symbols; today a hard-coded constant (an existing test already objects to it) | yes |
| 2 | `scripts/fund-search.py:68` `ASSET_CLASSES` | add `fx`, `energies`, `crypto` | yes |
| 3 | `scripts/fund-search.py:226` `build_cells` (this tree); on `b11-cell-spans`: `docs/architecture/fund-search-cells.json` + `load_cells_file` | 3 cell rows per class, each with `dev_start`, `rationale`, `decision`; validators already accept them once 1 and 2 are done | yes / hashed in the plan |
| 4 | `scripts/fund-search.py:103` `PRIOR_COUNTS` | the 180 prior prop-search records and 30 diagnosis slices concern the original 7 symbols; state that in the disclosure (new symbols had no prior search). Do not fold into N | yes |
| 5 | `scripts/fund-search.py:106` `fixed_opts` and `COST_PROFILE` (`:71`) | one profile for every cell. See 6 | yes |
| 6 | `scripts/real_costs.py:79` `PROFILES`, `:163` `profile_snapshot` | the snapshot hashes `symbol-map.json` and every spec file; changing the map of `ftmo_demo_2026_09` changes the recorded provenance of runs on the old 7 symbols. Profiles are month-versioned on purpose (module docstring), so the new specs belong in a **new profile** (`ftmo_demo_2026_10`, its own spec dir and map) that also covers the old 7, or a profile that chains two dirs. Open decision, see E.2 | yes |
| 7 | `scripts/real_costs.py:260` `swap_price` | implements `swap_mode == 1` (points) only and raises `CostRefused` otherwise. Any FX/crypto spec with another mode cannot be priced until a mode is added from sourced MQL5 semantics and checked against FTMO's own swap figures. The importer flags `spec_swap_mode_unsupported` | yes |
| 8 | `scripts/real_costs.py:284` `commission_r` | always `(0.0, status)`; FTMO `no_deals` means unknown. It understates any symbol with a real commission. A sourced per-lot figure needs a sized-cost path | yes |
| 9 | `scripts/real_costs.py:238` `spread_price` | takes no date: one recent per-UTC-hour spread summary prices the whole history. `ExportSymbolSpec.mq5` summarises 100,000 M15 bars, about 2.9 years of a 7-day tape or 4 years of a 5-day tape (arithmetic), against development history that can start years earlier | yes |
| 10 | `scripts/fund-search.py:106` `fixed_opts` -> `flat_before_rollover` + `rollover_provider` (`scripts/real_costs.py:203` `crosses_rollover`) | already provider-agnostic (server-local date compare). For crypto the FTMO server midnight is an arbitrary clock event, not a market close: every crypto trade is cut there. Acceptable as the account rule, but it removes holds across it and must be disclosed per cell | yes |
| 11 | `scripts/backtest-methods.py:1064` `b7_kz` | killzone entries are tested for `asset_class == "indices"` only. For fx/energies/crypto the ICT grid item B7 produces identical results for both values, yet is counted in the 29 per cell. Either keep N (conservative, no pre-registration change) or declare a class-specific N before `declare` | yes |
| 12 | `docs/architecture/sessions.json` (`weights`, `gates.weekend`) and `scripts/chart.js:32` `KZ_WEIGHT` (generated by `scripts/sync-sessions.py`) | weights exist for `crypto` (Binance-derived) and `metals` only; any other class gets `_default` = none. `gates.weekend` (Sat/Sun UTC) applies to **all** classes, crypto included, so session credit is withheld at weekends for a tape that may trade then. If the FTMO crypto class keeps the id `crypto` it silently inherits the Binance weights | no (registry data) |
| 13 | `docs/architecture/instruments.json` `canonical`, `display`, `analysis.cfd` | new rows (proposed by the importer, not applied); `display.asset_class` gets the values `fx`, `energies`, `crypto` | no |
| 14 | `scripts/prop-search.py:113`, `:122` | see A.0: candidate space follows `analysis("cfd")` | yes |
| 15 | `scripts/history_store.py` | **no change**: `resolve`, `read_doc`, `digest` are symbol-agnostic (`ohlcv.<SYM>.<TF>/`). Verified by reading, not by running new symbols | n/a |
| 16 | the live path's registry: `integrations/mt5/OrderBridge.mq5` `InpAllowedSymbols`, `scripts/automation.py:131`, `scripts/build-artifact.py:125`, `docs/architecture/schemas/*.json` (derived by `scripts/sync-instruments.py`), `docs/architecture/providers.json` `mt5_bridge_ftmo._needed_symbols_why`, `integrations/mt5/ExportOHLCV.mq5` (one chart per symbol) | none for research. Execution needs a separate owner decision; the order bridge allowlist is a compiled input that mirrors the **execution** list, which this work never touches | partly |
| 17 | `scripts/tests/test_instruments_sync.py`, `test_build_artifact.py` | update the forex-removal guards and the "no feed" expectations deliberately, in the change that adds the symbols | n/a |

Costs in R need no FX pip value: `cost_r` converts price-unit spread and swap to a fraction of entry, divided by the stop distance
(`scripts/real_costs.py:292`). What is missing for FX is not a pip table but a sourced swap mode and commission (rows 7 and 8).

Memory and time: a worker holds about 741 bytes per bar (`scripts/scan_many.py` comment, measured: 1m, 4.10 M bars = 3.0 GiB). A 24 h
FX 1m series can reach the 5,000,000-bar export cap, so about 3.5 GiB per worker per series (741 B/bar); the compute plan must budget for it.

### A.4 Order of work (all before `declare`; the ledger has no `fund_search` declaration yet)

1. Owner fixes the **classes and the symbol selection rule** from the listed depth and costs, not from any result.
2. TechLead/owner decide E.1 (registry shape) and E.2 (cost profile).
3. Registry rows, specs, history imported; `import-ftmo-symbols.py --require-history` exits 0.
4. Constants, cells rows, `PRIOR_COUNTS` note, tests; `fund-search.py plan --dry-run` shows the new N.
5. Only then `declare`.

## B. What it costs in N

Per-cell N is ICT 29 and Wyckoff 16 (`docs/plans/2026-09-30-owner-decisions.md`, section "planned R:R floor"; `n_total = per_cell x
n_cells`). The one-sided confidence is `1 - 0.10/N` (`scripts/fund_stats.py` `FAMILY_ALPHA`). Each **new class** adds 3 cells.

| New classes | Cells | ICT N | ICT confidence | Wyckoff N | Wyckoff confidence | Needed trades vs today for the same edge (ICT / Wyckoff) |
|---|---|---|---|---|---|---|
| 0 (six-cell base when written; today 3 cells: 87 / 0.998851, 48 / 0.997917) | 6 | 174 | 0.999425 | 96 | 0.998958 | 1.00 / 1.00 |
| +1 | 9 | 261 | 0.999617 | 144 | 0.999306 | 1.07 / 1.08 |
| +2 | 12 | 348 | 0.999713 | 192 | 0.999479 | 1.12 / 1.13 |
| +3 (fx, energies, crypto) | 15 | 435 | 0.999770 | 240 | 0.999583 | 1.16 / 1.18 |

The last column is the ratio of squared normal quantiles of the confidence level (3.251 -> 3.365 / 3.443 / 3.503 for ICT; 3.078 ->
3.197 / 3.279 / 3.341 for Wyckoff). It is a large-sample reference only: the harness bound is a one-sided Student-t bound on the
mean (`scripts/fund_stats.py`), slightly stricter at small n. Reading it: the first extra class needs 7-8% more trades to clear the
bound, which is cheap **if the class brings independent trades**, and a pure loss if it does not.

- Adding symbols to an **existing** class (more metals, more indices) adds **no N**: cells are class x timeframe and symbols are
  pooled inside a cell. It changes `m`, the stability denominator (`ceil(2m/3)` symbols must be positive), and pools more trades.
- A new class always adds N, whatever its symbol count. A class with 2 symbols pays the same 3 cells as one with 30; the symbol
  count of a class decides its power, not its cost.
- A cell with no symbol with development history before 2024-03-01 is removed from N by data availability (plan section 6 item 7),
  so a class of young symbols can drop out for free; a cell that stays and ends `insufficient` (fewer than 30 trades in a test fold)
  still counted in N.

## C. Risks

1. **Crypto CFD hours and weekends.** FTMO crypto-CFD hours are not assumed 24/7: the symbol list records `sessions_trade` and the
   importer reports every gap. The cfd market is `continuous: false` in the registry, so `quality.assess` never grades a hole in a
   crypto CFD as PARTIAL (`scripts/quality.py`); the importer's `long_gap` and `crypto_cfd_hours` checks are the only guard.
2. **FTMO crypto fees.** Swap mode, swap size and commission are unknown until exported. A non-points swap mode refuses to price
   (row 7). Spreads on crypto vary by hour; the spec carries a median and p90 per UTC hour from at most 100,000 M15 bars (row 9).
3. **Commission is unknown** for every FTMO spec (`no_deals`); the engine charges 0.0 and says so. FX and crypto may well charge one.
   Nothing in this work estimates it.
4. **Correlation: effective n.** USD majors, US indices and BTC/ETH move together. Pooled trades are not independent; for k
   equicorrelated series the usual design effect is `n_eff = n / (1 + (k-1) rho)` (a rule of thumb; no rho was measured here: for
   illustration only, k = 5, rho = 0.7 gives 0.26 n). More symbols in a class raise trades, not independence; stability counts
   symbols, so correlated winners look like several confirmations.
5. **Data depth varies.** First-bar dates differ by symbol and timeframe (the "Listed depth before export" table). A cell starts at
   its earliest symbol, folds follow, later symbols enter with fewer early bars (disclosed in `symbol_first_bar` on the cells branch).
   The existing XAUUSD/XAGUSD 1m series are already truncated by the 5,000,000-bar export cap, and the importer flags that.
   Measured on the real tree: GER40 has a 4776 h hole (2018-05-31 to 2018-12-16) and US30 a 410 h hole (2019-08-09 to 2019-08-26) in
   the 1m to 1W series of those symbols; the coverage audit does not mention them; they predate the 2024-03-01 cutoff and sit inside the development span.
6. **Costs only from FTMO exports.** No spec, no symbol: `real_costs.spec()` refuses. Do not borrow MetaQuotes or Binance numbers.
7. **Selection.** Choosing symbols after seeing results is data snooping. The rule must be written first (e.g. all symbols of the class
   with listed depth reaching before the cutoff), and `symbols_without_development` stays disclosed.
8. **Provenance caveats.** Tick volume, not traded volume; broker history exists only for instruments that still exist (survivorship);
   the server-clock convention was measured on metals and indices (`docs/audits/2026-09-29-ftmo-server-timezone.md`), not on FX or crypto bars.
9. **Registry side effects** (A.0) and the **name clash**: FTMO `BTCUSD` is a different instrument from Binance `BTCUSDT`; the importer
   refuses a CFD canonical name that is a Binance registry name, but the class id `crypto` is shared (row 12). Open decision E.3.

## D. Owner checklist

Exact commands and inputs are in `docs/architecture/mt5-ftmo-symbol-universe-export.md`; this is the order and what each step produces.

1. Compile the three `.mq5` files in MetaEditor (F7). Produces: `.ex5`, or compiler errors to send back (the new code is untested).
2. Run **ExportSymbolList** on any chart. Produces `Common\Files\symbollist.FTMO-Demo.json` (every symbol: path, contract terms, swap,
   sessions, first bar of M1/M5/M15, first date on the server).
3. Run `scripts/import-ftmo-symbols.py --symbol-list ...`. Produces `report.md/json` (classes, unmapped classes, collisions, canonical names,
   depth before export), `registry.patch.json`, `symbol-map.patch.json`, `*.diff`, `export-batches.txt`. Nothing is applied.
4. Decide classes and symbols (section A.4 step 1). Send back the symbol list and the report folder.
5. After the registry decision, `--apply` the reviewed patch and `sync-instruments.py --write`. Produces updated registry and map
   (backup in `<out>/backup/`).
6. Run **ExportSymbolSpec** with a batch line. Produces `symbolspec.<RAW>.json` -> `data/history/costs/ftmo/`.
7. Run **ExportHistory** with the same batch (8 timeframes `1m 5m 15m 30m 1H 4H 1D 1W`). Produces `history.<RAW>.<TF>.json`; keep the
   Experts-tab receipt lines.
8. `import-mt5-history.py --provider mt5_bridge_ftmo ... --split-threshold-bytes 0 --write`. Produces `data/history/ftmo/ohlcv.<CANON>.<TF>/`.
9. `import-ftmo-symbols.py --require-history`. Produces the post-import validation; exit 0 is the gate.
10. Send back: symbol list, receipt lines, both report folders, compiler messages. Do not commit raw or gz history without a storage
    decision (about 50 MB per symbol, 349 MB for the existing 7).

## E. Open decisions (not mine to take)

1. Registry shape for research-only symbols (A.0 a or b).
2. One new cost profile or a chained profile (row 6), and who exports the old 7 specs again if the profile must cover them.
3. `crypto` vs a distinct class id for FTMO crypto CFDs (row 12); whether FX/energies get session windows at all (ICT timing stays none).
4. Whether N stays 29/16 per cell for classes where B7 is inert (row 11).
5. Where the new history lives (repo size).
6. Which classes: each costs 3 cells of N (section B); `energies` may have too few symbols to be worth it.

## Evidence

Validation of the existing 7 symbols with the new importer: 0 ERROR, mapping reproduced (`US500.cash -> US500`, `US100.cash -> USTEC`,
`GER40.cash -> DE40` ...), AUS200 reported `spec_only`; WARNs are the real long gaps above and the 5,000,000-bar cap. Tests:
`scripts/tests/test_import_ftmo_symbols.py`.
