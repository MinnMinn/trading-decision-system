# MT5 File-Bridge — commodities/CFD market data

Referenced by `docs/architecture/SYSTEM-DESIGN.md` §3 and `data-sources.md`.

## Order bridge (2026-09-11, user decision: real orders on the MT5 DEMO account)

`integrations/mt5/OrderBridge.mq5` is a second EA, attached to any one chart, that turns the same Common\Files folder into an order channel: `scripts/mt5-order-bridge.py` writes `bridge/cmd-<id>.json` (temp file + rename), the EA polls every second, executes, writes `bridge/res-<id>.json` and deletes the command; it also refreshes `bridge/state.json` (account, positions, orders) and `bridge/symbols.json` (tick size/value, volume min/max/step, digits). Verbs: `check | account | state | symbol | limit <SYM> <buy|sell> <LOTS> <PRICE> <SL> <TP> [COMMENT] | market <SYM> <buy|sell> <LOTS> <SL> <TP> [COMMENT] | cancel | modify | close | order-status | position-status` (`market` = Wyckoff entries at the bar close, SL/TP attached). Hard limits live in the EA (`InpDemoOnly`, symbol allowlist, `InpMaxLots`, magic number, SL/TP mandatory on every pending order) and are repeated on the Python side (allowlist, timeout → exit 3, a timed-out command file is removed so a later EA start never executes it). Consumer: `scripts/strategy-runner.py` (pilot profile `top20`, CFD setups, `execution: "mt5"`).

Install: copy `OrderBridge.mq5` next to `ExportOHLCV.mq5` in `MQL5/Experts/`, compile in MetaEditor, attach to one chart of the demo account, allow algo trading, then `python3 scripts/mt5-order-bridge.py check` must print `"demo": true`. **Status: verified 2026-09-11 on the demo account (login masked, $100k, USD):** compiled through MetaEditor via the bundled Wine (0 errors); `check` → demo true; pending BUY LIMIT 0.01 lot far below market placed (retcode 10009), read back `pending`, cancelled, read back `canceled`; market BUY 0.01 with SL/TP filled at 4351.87, SL modified (breakeven path), closed by the bridge (reason `expert`, P&L −0.50 = spread), account back to no orders/positions. Two things learned: the terminal needs the toolbar **Algo Trading** button on and the EA's "Allow Algo Trading" ticked (else retcode 10027), and this broker lists XAUUSD/XAGUSD but not USOIL/UKOIL (the EA's `symbols.json` only carries symbols `SymbolSelect` accepts). The EA escapes backslashes/quotes in JSON strings since the fix that followed the first live ping; the connector also tolerates an older build. Python side covered by `scripts/tests/test_strategy_runner.py` (fake EA).
 This replaces the earlier "commodities provider TBD via Alpha Vantage/Twelve Data/etc." plan with a more direct approach: **pull the data straight out of the MT5 terminal you're actually trading on**, via a small Expert Advisor that writes JSON files, the same way the Binance connector writes files for crypto. No third-party commodities API, no extra account, no extra API key.

## Why a file bridge, not the official MetaTrader5 Python package

MetaQuotes' official `MetaTrader5` Python package only works on **Windows** — it talks to a locally-running MT5 terminal via a DLL. This environment is macOS, so that package won't work directly here. The file-bridge approach (an MQL5 script inside MT5 writes JSON; this system reads the JSON) works regardless of OS, at the cost of needing a manual or scripted sync step to get the files from wherever MT5 runs into this project.

## Components

1. **`integrations/mt5/ExportOHLCV.mq5`** — an Expert Advisor you attach to one chart of the instrument you want (e.g. XAUUSD, any timeframe). It exports **six** timeframes (1W/1D/4H/1H/15m/5m — 5m and 1W added 2026-09-11 for the CFD scalping page and the swing context chart; recompile in MetaEditor and re-attach after pulling that change) for that symbol on a timer and on every new bar close, into files named `ohlcv.<SYMBOL>.<TIMEFRAME>.json` in MT5's shared "Common\Files" folder — the *exact same field shape* as the Binance connector's output, so Skills don't need to know or care which venue the data came from.

   **Status: written, not yet tested against a real MT5 terminal.** Install it, attach it to a chart, check the Experts/Journal log tab for errors or the printed "Common data folder" path, and tell me what happens — I'll fix anything that doesn't work first try.

2. **A sync step** (you'll need to pick the one matching your setup — I don't know which you have):
   - **MT5 runs natively on a Windows PC/VM, this Claude Code session runs on your Mac**: use a shared folder (VM shared folder, SMB share, cloud-sync folder like Dropbox/OneDrive pointed at both locations) to get the 4 JSON files from MT5's `Common\Files` folder into this project's `data/live/mt5-bridge/`.
   - **MT5 runs as a Mac-native app** (many brokers ship a Wine-wrapped "MetaTrader 5 for Mac" — it looks native but is Wine underneath): the Common\Files folder lives inside that app's Wine prefix on the same Mac. The EA's startup log prints the exact path via `TerminalInfoString(TERMINAL_COMMONDATA_PATH)` — once you have that path, either symlink it directly (`ln -s "<that path>/Files" data/live/mt5-bridge`) or copy the 4 files over periodically.
   - Whichever you use, tell me the concrete path once you find it and I'll wire up whichever sync mechanism fits (symlink is simplest if it's all on one machine).

   **Resolved on 2026-09-09 (this Mac):** MT5 for Mac is installed as a Wine-wrapped app; its prefix is
   `~/Library/Application Support/net.metaquotes.wine.metatrader5/`. Concrete paths:
   - terminal + MetaEditor: `<prefix>/drive_c/Program Files/MetaTrader 5/{terminal64.exe,metaeditor64.exe}`
   - EA source installed at: `<prefix>/drive_c/Program Files/MetaTrader 5/MQL5/Experts/ExportOHLCV.mq5` (copy of `integrations/mt5/ExportOHLCV.mq5`)
   - Common data folder: `<prefix>/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files`
   - `data/live/mt5-bridge` is now a **symlink** to that `Common/Files` folder — no copy step needed; the EA's output appears in the project instantly.
   - `scripts/mt5-bridge-check.sh [SYMBOL] [MAX_AGE_SEC]` reports AVAILABLE / STALE / UNAVAILABLE per timeframe (this is the freshness check `data-validation-status` expects).
   - `integrations/mt5/startup-ExportOHLCV.ini` + `ExportOHLCV.set` (also copied into the terminal's `config\` and `MQL5\Presets\`) auto-attach the EA to XAUUSD H1 when the terminal is started with `/config:startup-ExportOHLCV.ini`.
   Still required by hand (GUI): compile the EA once in MetaEditor (F7) and attach it to a chart; the EA is untested until that first run.

   **Timestamp caveat (fixed in EA v1.01):** `CopyRates` times and `TimeCurrent()` are broker *server* time, not UTC. The EA now subtracts the live `TimeCurrent() - TimeGMT()` offset before writing the `...Z` strings and records `_server_utc_offset_sec` in each file, so bridge timestamps line up with the Binance connector's UTC.

3. **Where this system reads from**: `data/live/mt5-bridge/ohlcv.<SYMBOL>.<TIMEFRAME>.json` (mirrors `data/live/market-data/` for crypto). `/analyze` and `/status` check this path's freshness before falling back to `UNAVAILABLE`.

## Staleness rule

Same as the crypto contract: `now − last_updated > 1.5× the timeframe's own bar interval` → `STALE`, not `AVAILABLE`. Since the EA only writes when the terminal is running and connected, a stale file usually just means the terminal was closed — report it plainly rather than serving old data as current.

## Hard caveat: `volume` here is NOT real traded volume

Most CFD/commodity brokers report `real_volume = 0` to MT5 — there is no consolidated tape the way Binance has one. The EA falls back to `tick_volume` (count of price changes, not actual size traded) and flags this explicitly in each output file's `_volume_caveat` field.

**This is the exact same limitation the ingested Wyckoff book itself warns about** (`knowledge/wyckoff/modern-tools.md` §7 and §3.2 — the book flags Forex's tick-based Delta as not real traded volume and therefore unreliable for Footprint/Delta analysis, WMT p131–p132; paraphrased, not a verbatim quote). `wyckoff-skill` and `ict-skill` should weight Effort-vs-Result evidence sourced from `mt5_bridge_live` data lower than the same evidence sourced from Binance's real trade volume, and say so explicitly in their output rather than treating the two as equivalent.

## What this does — and doesn't — unlock

- **Wyckoff + ICT dimensions**: fully usable once the bridge is live, with the volume caveat above applied to Wyckoff's Effort-vs-Result scoring.
- **Footprint + Heatmap dimensions**: still **not available** for MT5/CFD instruments. CoinGlass (Footprint history, liquidation heatmap, orderbook heatmap) is crypto-derivatives-only — there is no equivalent wired up for MT5. `footprint-skill` and `heatmap-skill` must report `UNAVAILABLE` for XAUUSD/XAGUSD/USOIL/UKOIL regardless of how good the MT5 bridge is.
- **Practical consequence**: even with this bridge fully live, XAUUSD/XAGUSD/USOIL/UKOIL analysis is capped at **2 of 4 dimensions (Wyckoff + ICT)** — enough for **NORMAL mode** (needs ≥2), but **ENHANCED and STRICT mode are structurally unreachable** for these instruments until a genuine order-flow/liquidity data source for MT5 markets is found (a tick-data-derived Footprint approximation is theoretically possible — some third-party MT5 indicators do this — but is a separate, unbuilt piece of work, not something this bridge provides).

## Execution (a separate, later question)

This bridge is **read-only** — it exports market data, it does not place orders. Semi-automated execution via MT5 (e.g. an EA that reads a ticket file this system writes and places the order) is a materially bigger step: it would give this system's output a path to real money movement, which is exactly the kind of trust-boundary change `docs/architecture/SYSTEM-DESIGN.md` §9 and this project's own routing rules require a Security review for before building. Don't wire that up without raising it explicitly first.


## Verified on a real terminal (2026-09-10 03:52Z)

`ExportOHLCV` v1.01 attached to XAUUSD H1 in MetaTrader 5 (macOS build, prefix
`~/Library/Application Support/net.metaquotes.wine.metatrader5`). `scripts/mt5-bridge-check.sh XAUUSD` → AVAILABLE
for 1W/1D/4H/1H/15m/5m, files refreshed every 60 s (`last_updated`), 300 candles each (EA input `InpBarsToExport`, raised from 200 on 2026-09-11 so the 288-bar 15m and 5m windows are full).
Checked: timestamps are UTC (`_server_utc_offset_sec: 10800`, i.e. server UTC+3 — the 15m candle open times match
the wall clock, the daily candle opens at 21:00Z = broker midnight), all six fields present, `_volume_caveat`
present (tick volume, not traded volume — Effort-vs-Result reads on gold use it as a proxy only).
The deterministic scanner reads the bridge directly (`scripts/ict-scan.py` `load()` routes XAUUSD/XAGUSD/USOIL/UKOIL
to `data/live/mt5-bridge/`); **since 2026-09-13 the CFD side runs the same three horizons as crypto and nothing
else** — the launchd loop scans `cfd-scalping` (15m) at :01/:16/:31/:46, `cfd-day` (1H) at :02 every hour and
`cfd-swing` (4H) at :03 of every 4th hour (`scan-loop.sh:106-110` (`run_style 15m scalping`)), emitting events to
`data/live/events.jsonl` like the crypto styles. The style names are derived from one authored table,
`automation.HORIZON_TF` (`automation.py:142` (`HORIZON_TF = {"scalping": "15m"`)) — read that, do not re-list them
here. Bar counts per timeframe come from `automation.SCAN_WINDOW` (`automation.py:154` (`SCAN_WINDOW = {`)). Which
of the three actually run is gated per timeframe by `/automation` (`markets.cfd.timeframes`, keys `15m`/`1h`/`4h`),
and the symbols come from `markets.cfd.instruments` — a symbol with no bridge file on disk is skipped rather than
aborting the style (`scan-loop.sh:84` (`if [ -s "data/live/mt5-bridge/ohlcv.`)). There is no CFD 1m style: the EA
does not export 1m (SYSTEM-DESIGN.md §12 item 6). `1D` and `1W` stay as **context rungs** — exported and drawn,
never scanned. No CFD chart artifact exists yet; `scripts/local-eval-brief.py cfd-scalping` (and `cfd-day` /
`cfd-swing`) already produces the Sonnet brief, though only `cfd-scalping` has a headless prompt pair in
`integrations/headless/`, so it is the only CFD style whose local read actually runs.
