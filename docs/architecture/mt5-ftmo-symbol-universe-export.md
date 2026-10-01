# Adding the full FTMO CFD universe and FTMO crypto CFDs: owner export procedure

**Status of the MQL5 in this procedure: UNTESTED.** `integrations/mt5/ExportSymbolList.mq5` (new) and the batch mode
added to `integrations/mt5/ExportHistory.mq5` (v1.01) were written without MetaEditor or MT5 and have never been
compiled. Compile each in MetaEditor first (F7) and send back any compiler message verbatim. `ExportSymbolSpec.mq5` is
unchanged and was run on 2026-09-28 (its output is the 8 `symbolspec.*.json` files already in the repo).

Why: owner decision 2026-10-01, add "full" FTMO CFDs and crypto CFDs to raise statistical power. What it costs the
statistics, and every code point that has to change before any of it counts, is in
`docs/plans/2026-10-01-symbol-universe-design.md`. This page is only the mechanical procedure.

The Binance USDT history under `data/history/ohlcv.*USDT.*` is **not** FTMO crypto and is never used here.

## Prerequisites

- The terminal is logged in to the **`FTMO-Demo`** server. The importer refuses any other server name
  (`scripts/mt5_time.py` `check_server`): the declared clock convention is a claim about that one server.
- Tools > Options > Charts > **Max bars in chart = Unlimited**, then **restart the terminal** (a stale cache keeps the old
  cap; `docs/architecture/mt5-history-export.md`, "What the first export actually produced").
- Disk: the first FTMO export wrote a raw M1 file of about 300 MB per symbol (ExportHistory.mq5 header comment). Export in
  batches and delete the raw `history.*.json` files after each import.
- `InpBars` in ExportHistory is 5,000,000. A series with exactly that many bars was cut at the cap and is missing its
  OLDEST history (this already happened to XAUUSD/XAGUSD 1m, `docs/audits/2026-09-29-ftmo-history-coverage.md`); the
  validator warns `bars_hit_export_cap`. By arithmetic (not measured on this account), a 24 h x 5 day FX M1 series reaches 5M bars after about 13
  years and a 24 h x 7 day crypto series after about 9.5 years.

## Steps

Every file name below is relative to the terminal's **Common\Files** folder (the scripts print it on their first Experts
line).

| # | Where | Action | Produces |
|---|---|---|---|
| 1 | MetaEditor | File > Open Data Folder > `MQL5\Scripts`; copy `ExportSymbolList.mq5`, `ExportHistory.mq5`, `ExportSymbolSpec.mq5` from `integrations/mt5/`; compile each (F7) | `.ex5` files, or compiler errors to send back |
| 2 | MT5 | Navigator > Scripts > drag **ExportSymbolList** onto any chart; keep the defaults (`InpOnlyMarketWatch=false` lists every symbol on the server; `InpProbeHistory=true` briefly selects each symbol to read its first-bar dates) | `symbollist.FTMO-Demo.json`; Experts tab: `ExportSymbolList: N symbol(s) ...` then `done` |
| 3 | repo | `python3 scripts/import-ftmo-symbols.py --symbol-list <path to symbollist.FTMO-Demo.json>` (optionally `--classes fx,crypto`, `--symbols A,B`, `--override RAW=CANON`, `--class-alias "<path head>=<class>"`) | in `<system tmp>/import-ftmo-symbols/` (or `--out`): `report.md`, `report.json`, `registry.patch.json`, `symbol-map.patch.json`, `registry.diff`, `symbol-map.diff`, `export-batches.txt` |
| 4 | repo | Read `report.md`: unmapped classes (excluded, listed), name collisions (ERROR, block both symbols), proposed canonical names, and the **Listed depth before export** table (first M1/M5/M15 bar per symbol). Choose the symbols to export (not necessarily all) | the symbol selection |
| 5 | repo | **Needs a go-ahead; edits `docs/architecture/instruments.json`.** Read the side effects in the design doc section A.0 first. `python3 scripts/import-ftmo-symbols.py --symbol-list ... --apply`, then `python3 scripts/sync-instruments.py --write` | backup of both files in `<out>/backup/`; registry + `data/history/costs/ftmo/symbol-map.json` updated. Required BEFORE step 8: `import-mt5-history.py` refuses a symbol that is not on the allowlist |
| 6 | MT5 | Drag **ExportSymbolSpec** onto a chart; `InpSymbols` = one `batch-NN` line from `export-batches.txt` | `symbolspec.<RAW>.json` per symbol |
| 7 | MT5 | Drag **ExportHistory** onto a chart; `InpSymbols` = the same batch line; leave W1/D1/H4/H1/M30/M15/M5/M1 all true (the 8 timeframes the existing 7 symbols have: `1m 5m 15m 30m 1H 4H 1D 1W`); `InpBars` stays large | `history.<RAW>.<TF>.json`, 8 per symbol. Experts tab, one receipt line per series: `<RAW> <TF> -> N bars, first .. last (server time)`. **Keep those lines** |
| 8 | repo | Copy `symbolspec.*.json` into `data/history/costs/ftmo/`. Copy `history.*.json` into `data/live/mt5-bridge/` (the importer's default `--src-dir`; use `--src-dir` for another folder). Dry run, then write: `python3 scripts/import-mt5-history.py --provider mt5_bridge_ftmo --symbol-map data/history/costs/ftmo/symbol-map.json --dest-root data/history/ftmo --split-threshold-bytes 0 [CANONICAL ...]` and again with `--write` (flags from `docs/audits/2026-09-29-ftmo-history-coverage.md` and `scripts/import-mt5-history.py main()`) | `data/history/ftmo/ohlcv.<CANON>.<TF>/` (index.json + one `<year>.json.gz`), server time converted to UTC |
| 9 | repo | Verify: `python3 scripts/import-ftmo-symbols.py --symbol-list ... --require-history`. Exit 0 means no ERROR for the selected symbols | `report.md`: per symbol which timeframes exist, bar counts, first/last, duplicates, gaps, spec present, swap mode supported |
| 10 | you | Send back: the `symbollist` file, the Experts-tab receipt lines (or the terminal's `MQL5\Logs` file), the step-3 and step-9 report folders, any compiler message | what is needed to decide the cells |

Repeat 6 to 8 per batch. If the terminal rejects a long `InpSymbols` value (the input-string length limit is not
verified), use smaller batches: `--batch-size N` on the importer sets the batch length.

## What is checked, what is not

- `import-ftmo-symbols.py` flags as ERROR: a name collision, a bad canonical name, a symbol with history but no
  decision timeframe (1m/5m/15m), an INVALID series (duplicate or backwards timestamp, broken OHLC), a missing spec, a spec
  whose `swap_mode` is not 1 (`scripts/real_costs.py` swap_price raises on any other), a spec with no recorded spread.
  WARN: a gap above 4 days (intraday; 5 days for 1D, 15 for 1W), a missing context timeframe, a series cut at the export cap.
- It never decides the cost model. The commission of every FTMO spec so far is `no_deals` (unknown) and the engine
  charges 0.0; that understates the cost of any symbol that really has one. FX and crypto commission and swap terms must
  come from the exported spec or FTMO's contract page, never from a guess.
- The server-to-UTC conversion uses the convention measured for this server
  (`docs/audits/2026-09-29-ftmo-server-timezone.md`) on metals and indices bars. The same server clock stamps crypto and FX
  bars; the convention has not been separately measured on them.
- Size: the 7 existing symbols occupy 349 MB in `data/history/ftmo` (audit above), about 50 MB per symbol after gzip,
  1m being two thirds. A hundred symbols is several GB: decide where the new history lives before anything is committed to
  a public repo.
