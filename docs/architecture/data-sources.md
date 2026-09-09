# Data Sources — Exchange-native market data & CoinGlass (contract + mock mode)

Referenced by `docs/architecture/SYSTEM-DESIGN.md` §3. This is the stable interface Skills are built against, so swapping mock fixtures for a real API connector later changes only the connector, never the Skills.

**Revision note:** the original design targeted a TradingView MCP for price/candle data. That was dropped — TradingView has no official public data API for third parties, and the community MCP servers that exist do so via browser automation or unofficial scraping (fragile, possible ToS risk). This system now uses **exchange-native REST APIs** instead: Binance's free public REST API for crypto, and a commodities provider **to be selected** for XAUUSD/XAGUSD/USOIL/UKOIL (see below — this is an explicit open gap, not silently resolved).

## Status: no real connectors configured yet

Neither a crypto exchange connector, a commodities data provider, nor a CoinGlass API key is present in this environment as of this writing. All sources run in **MOCK mode** against the fixtures under `mock/`. This is a real, load-bearing limitation, not a formality — see the integrity rule below.

## Mock-mode integrity rule (hard rule, not a style choice)

Every Data Validation Status block this system emits MUST use one of exactly four states per source: `AVAILABLE` | `STALE` | `UNAVAILABLE` | `MOCK`. `MOCK` means "fixture data, not live" and is fundamentally different from `AVAILABLE` — a dimension fed by `MOCK` data can complete a **rehearsal** run of the pipeline (useful for testing the Skills/Agents themselves) but can **never** satisfy the Independent-Confluence Check for a live trade decision (`SYSTEM-DESIGN.md` §6.1). Any `/analyze` output produced while any required source is `MOCK` must carry a top-of-output banner: `⚠ REHEARSAL MODE — mock data in use, not a live signal.` This is what lets the system be built and tested end-to-end before real credentials exist, without ever risking a mock-fed output being mistaken for tradeable.

## Crypto market-data contract (BTC/ETH/SOL) — LIVE, connector built and verified

Used for: price/candles, market structure, timeframes, technical context. **Real integration is live**: `scripts/fetch-binance-klines.sh <SYMBOL> <TIMEFRAME> [LIMIT]` calls Binance's public REST API (`/api/v3/klines` — no auth required, no API key needed) and writes normalized output to `data/live/market-data/ohlcv.<SYMBOL>.<TIMEFRAME>.json`. Tested against BTCUSDT/ETHUSDT/SOLUSDT with real current data; fails loudly (nonzero exit, no output file written) on a bad symbol or network error rather than silently producing empty/wrong data.

| Field | Type | Notes |
|---|---|---|
| `symbol` | string | e.g. `BTCUSDT` |
| `timeframe` | string | `1D`, `4H`, `1H`, `15m` per the master spec's MTF framework; the live connector also accepts `5m` and `1m` (used by the scalping report) |
| `candles[]` | array of `{time, open, high, low, close, volume}` | volume here is exchange-reported bar volume, not order-flow — Footprint/Delta come from CoinGlass, not this |
| `last_updated` | ISO8601 timestamp | staleness = now − last_updated > 1.5× the timeframe's own bar interval |
| `_source` | string | `"binance_public_rest_live"` when written by the real connector — distinguishes it from a mock fixture without needing a separate directory check |

**How commands should use this:** before falling back to `mock/market-data/`, run `scripts/fetch-binance-klines.sh <SYMBOL> <TIMEFRAME>` and read `data/live/market-data/ohlcv.<SYMBOL>.<TIMEFRAME>.json` if the fetch succeeds (exit 0, `_source: "binance_public_rest_live"` present) — this is `crypto_market_data: AVAILABLE`, not `MOCK`, and DOES count toward the Independent-Confluence Check. A nonzero exit or missing `_source` field means the fetch failed — report `UNAVAILABLE`, do not fall back to a stale live file silently.

Mock fixtures remain at `mock/market-data/ohlcv.<SYMBOL>.<TIMEFRAME>.json` for rehearsal/testing when you deliberately want to exercise the pipeline without hitting the network.

## Commodities market-data contract (XAUUSD/XAGUSD/USOIL/UKOIL) — MT5 file bridge

**Decision made:** rather than a third-party commodities API, this pulls data directly from your own MT5 terminal via a file bridge (an MQL5 Expert Advisor writes JSON files this system reads) — full design, install steps, and hard caveats in **`docs/architecture/mt5-bridge.md`**. Script: `integrations/mt5/ExportOHLCV.mq5` (written, not yet tested against a real terminal). Read path: `data/live/mt5-bridge/ohlcv.<SYMBOL>.<TIMEFRAME>.json`. Same field shape as the crypto contract above, plus a `_volume_caveat` field since MT5's volume for CFDs is tick-count, not real traded size.

Do not substitute a tokenized crypto proxy (e.g. PAXG for gold) for real commodities data — that introduces basis risk and is not acceptable. Until the bridge file exists and is fresh, report `commodities_market_data: UNAVAILABLE`.

## CoinGlass contract

Used for: Footprint history, liquidation heatmap, orderbook heatmap, Delta/CVD, Open Interest, Funding. **Crypto-derivatives-only** — see the note at the bottom of this file for commodities.

| Endpoint (mock file) | Field | Notes |
|---|---|---|
| `footprint-history.<SYMBOL>.json` | `bars[]` of `{time, price_levels: [{price, bid_vol, ask_vol}], delta, cumulative_delta}` | feeds FootprintSkill's POC/R-H/R-L/Imbalance/Delta reads |
| `liquidation-heatmap.<SYMBOL>.json` | `clusters[]` of `{price, notional_est, side}` | feeds HeatmapSkill; `notional_est` is explicitly an estimate — never state a liquidation cluster's size as precise/confirmed |
| `orderbook-heatmap.<SYMBOL>.json` | `levels[]` of `{price, resting_size, side, snapshot_time}` | order-book liquidity concentration, separate from liquidation clusters — do not conflate the two as one signal (independent-confluence discipline) |
| `open-interest.<SYMBOL>.json` | `series[]` of `{time, oi}` | |
| `funding.<SYMBOL>.json` | `series[]` of `{time, rate}` | |

Mock fixtures: `mock/coinglass/`. Real integration target: direct REST using the user's CoinGlass API key (master spec §9) — not yet connected; when the key arrives, treat wiring it as a trust-boundary change (new external vendor + secret-handling, per this project's own routing rules) and route it through Security review before use. Store it the same way as the Binance testnet credentials (see "Secret storage" below) — never in a plaintext file, never in the conversation transcript if avoidable.

## Secret storage convention

All API credentials this project uses (Binance testnet key/secret today; CoinGlass key when it arrives) live in **macOS Keychain**, never in a plaintext file, never committed to git. Retrieve via `scripts/get-secret.sh <secret-name>` — callers must capture the output into a variable and never echo/print it.

Current entries (account `binance-testnet` in Keychain):
- `trading-system-binance-testnet-api-key`
- `trading-system-binance-testnet-secret-key`

When the CoinGlass key arrives, store it the same way (e.g. service name `trading-system-coinglass-api-key`) and add a fetcher script following `scripts/binance-testnet-order.sh`'s pattern (`get-secret.sh` inside the script, never a CLI argument, never printed to stdout/logs).

## No dedicated Heatmap/Liquidity knowledge-base source

Unlike Wyckoff/ICT/Footprint, there is no ingested book/course covering Heatmap/Liquidity theory in `docs/`. `HeatmapSkill`'s rules are sourced only from the master system prompt's own text (§2.4, §8). If the user adds a dedicated source later, ingest it the same way the Wyckoff book was ingested before trusting HeatmapSkill at STRICT mode.

## Instrument coverage in mock fixtures (v1)

`BTCUSDT` only, across `1D/4H/1H/15m` (market-data) and all five CoinGlass endpoints. This is enough to exercise the full pipeline end-to-end once. Add `ETHUSDT`, `SOLUSDT` fixtures the same shape when needed (both are Binance-coverable the same way as BTCUSDT). For `XAUUSD`/`XAGUSD`/`USOIL`/`UKOIL`: CoinGlass's `liquidation-heatmap`/`open-interest`/`funding` endpoints don't apply to commodities at all (crypto-derivatives-specific) — `HeatmapSkill` should report those `UNAVAILABLE`, not mocked, for these instruments; only `orderbook-heatmap` and `footprint-history` concepts could ever translate to a commodities venue, and only once a specific CFD/futures broker's real API is wired in — do not mock a CoinGlass-shaped commodities integration that doesn't exist.

## Chart refresh cadence & event triggers (2026-09-09)

Published report artifacts (scalping 1m/180, day-trade 15m/288, swing 1D/120) are kept current by two layers:

| Style | Data + preliminary read (Haiku, ~2 min, no LLM prose) | Full narrative (Sonnet) |
|---|---|---|
| Scalping | every 3 min, local cron | every 30 min local, **or immediately on a new structural event** |
| Day-trade | every 15 min, local cron | hourly cloud routine `day-trade-chart-refresh` (bounded verdict refresh), **run on demand on a new event** |
| Swing | every 4 h, local cron | daily 00:15 UTC cloud routine `swing-chart-refresh`, run on demand on a new event |

- `scripts/ict-scan.py --tf <tf> --n <bars> --style <style>` is the deterministic scanner (same rules as the artifacts' client-side `ictAnalyze`): 3-bar pivots, equal highs/lows (BSL/SSL) + ERL, sweeps, FVGs to mitigation, MSS, Order Blocks, premium/discount, volume outliers. It writes a Vietnamese preliminary read per symbol to `data/live/prelim/<style>.<SYM>.html` (with docs/ citations; thresholds flagged as system parameters) and exits 3 when a **new** sweep / ERL touch / MSS appeared since the last scan (state in `data/live/scan-state.<style>.json`). FVG formation and volume spikes feed the text only — they do not trigger alerts.
- `scripts/inject-prelim.py <artifact.html> <style>` places those snippets into `<div class="prelim">` blocks (idempotent).
- Event handling: a new structural event → one PushNotification (Vietnamese, ≤200 chars) + a full re-analysis (local Sonnet for scalping; `RemoteTrigger run` of the cloud routine for day-trade/swing). Dedup is at the scanner-state level, so the same event never alerts twice. Local crons are session-scoped and expire after 7 days; the cloud routines persist.
- Lesson from the first Haiku data patch: a *resumed* subagent had its Artifact publish blocked by the permission classifier; fresh dispatches publish fine — cron prompts therefore always dispatch a new agent.
