# MT5 File-Bridge — commodities/CFD market data

Referenced by `docs/architecture/SYSTEM-DESIGN.md` §3 and `data-sources.md`. This replaces the earlier "commodities provider TBD via Alpha Vantage/Twelve Data/etc." plan with a more direct approach: **pull the data straight out of the MT5 terminal you're actually trading on**, via a small Expert Advisor that writes JSON files, the same way the Binance connector writes files for crypto. No third-party commodities API, no extra account, no extra API key.

## Why a file bridge, not the official MetaTrader5 Python package

MetaQuotes' official `MetaTrader5` Python package only works on **Windows** — it talks to a locally-running MT5 terminal via a DLL. This environment is macOS, so that package won't work directly here. The file-bridge approach (an MQL5 script inside MT5 writes JSON; this system reads the JSON) works regardless of OS, at the cost of needing a manual or scripted sync step to get the files from wherever MT5 runs into this project.

## Components

1. **`integrations/mt5/ExportOHLCV.mq5`** — an Expert Advisor you attach to one chart of the instrument you want (e.g. XAUUSD, any timeframe). It exports **all four** timeframes (1D/4H/1H/15m) for that symbol on a timer and on every new bar close, into files named `ohlcv.<SYMBOL>.<TIMEFRAME>.json` in MT5's shared "Common\Files" folder — the *exact same field shape* as the Binance connector's output, so Skills don't need to know or care which venue the data came from.

   **Status: written, not yet tested against a real MT5 terminal.** Install it, attach it to a chart, check the Experts/Journal log tab for errors or the printed "Common data folder" path, and tell me what happens — I'll fix anything that doesn't work first try.

2. **A sync step** (you'll need to pick the one matching your setup — I don't know which you have):
   - **MT5 runs natively on a Windows PC/VM, this Claude Code session runs on your Mac**: use a shared folder (VM shared folder, SMB share, cloud-sync folder like Dropbox/OneDrive pointed at both locations) to get the 4 JSON files from MT5's `Common\Files` folder into this project's `data/live/mt5-bridge/`.
   - **MT5 runs as a Mac-native app** (many brokers ship a Wine-wrapped "MetaTrader 5 for Mac" — it looks native but is Wine underneath): the Common\Files folder lives inside that app's Wine prefix on the same Mac. The EA's startup log prints the exact path via `TerminalInfoString(TERMINAL_COMMONDATA_PATH)` — once you have that path, either symlink it directly (`ln -s "<that path>/Files" data/live/mt5-bridge`) or copy the 4 files over periodically.
   - Whichever you use, tell me the concrete path once you find it and I'll wire up whichever sync mechanism fits (symlink is simplest if it's all on one machine).

3. **Where this system reads from**: `data/live/mt5-bridge/ohlcv.<SYMBOL>.<TIMEFRAME>.json` (mirrors `data/live/market-data/` for crypto). `/analyze` and `/status` check this path's freshness before falling back to `UNAVAILABLE`.

## Staleness rule

Same as the crypto contract: `now − last_updated > 1.5× the timeframe's own bar interval` → `STALE`, not `AVAILABLE`. Since the EA only writes when the terminal is running and connected, a stale file usually just means the terminal was closed — report it plainly rather than serving old data as current.

## Hard caveat: `volume` here is NOT real traded volume

Most CFD/commodity brokers report `real_volume = 0` to MT5 — there is no consolidated tape the way Binance has one. The EA falls back to `tick_volume` (count of price changes, not actual size traded) and flags this explicitly in each output file's `_volume_caveat` field.

**This is the exact same limitation the ingested Wyckoff book itself warns about** (`knowledge/07-wyckoff-and-modern-tools.md` §7 and §3.2 — the book flags Forex's tick-based Delta as not real traded volume and therefore unreliable for Footprint/Delta analysis, WMT p131–p132; paraphrased, not a verbatim quote). `wyckoff-skill` and `ict-skill` should weight Effort-vs-Result evidence sourced from `mt5_bridge_live` data lower than the same evidence sourced from Binance's real trade volume, and say so explicitly in their output rather than treating the two as equivalent.

## What this does — and doesn't — unlock

- **Wyckoff + ICT dimensions**: fully usable once the bridge is live, with the volume caveat above applied to Wyckoff's Effort-vs-Result scoring.
- **Footprint + Heatmap dimensions**: still **not available** for MT5/CFD instruments. CoinGlass (Footprint history, liquidation heatmap, orderbook heatmap) is crypto-derivatives-only — there is no equivalent wired up for MT5. `footprint-skill` and `heatmap-skill` must report `UNAVAILABLE` for XAUUSD/XAGUSD/USOIL/UKOIL regardless of how good the MT5 bridge is.
- **Practical consequence**: even with this bridge fully live, XAUUSD/XAGUSD/USOIL/UKOIL analysis is capped at **2 of 4 dimensions (Wyckoff + ICT)** — enough for **NORMAL mode** (needs ≥2), but **ENHANCED and STRICT mode are structurally unreachable** for these instruments until a genuine order-flow/liquidity data source for MT5 markets is found (a tick-data-derived Footprint approximation is theoretically possible — some third-party MT5 indicators do this — but is a separate, unbuilt piece of work, not something this bridge provides).

## Execution (a separate, later question)

This bridge is **read-only** — it exports market data, it does not place orders. Semi-automated execution via MT5 (e.g. an EA that reads a ticket file this system writes and places the order) is a materially bigger step: it would give this system's output a path to real money movement, which is exactly the kind of trust-boundary change `docs/architecture/SYSTEM-DESIGN.md` §9 and this project's own routing rules require a Security review for before building. Don't wire that up without raising it explicitly first.
