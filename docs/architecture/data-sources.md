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

**Pilot-private copies (2026-09-11).** `scripts/fetch-binance-klines.sh` honours `KLINES_OUT_DIR`; `scripts/strategy-runner.py` (pilot profile `top5`) fetches 30m / 1H / 2H × 300 into `data/live/pilot-futures/candles/` and drops the forming candle, so the launchd scanner stays the single writer of `data/live/market-data/` and the pilot never reads a half-formed bar. 30m and 2H are pilot data only — no chart style, no local read, no artifact.

**Research history for CFD backtests (2026-09-11).** `scripts/fetch-history-cfd.py` pulls Yahoo Finance front-month futures (GC=F, SI=F, CL=F, BZ=F) into `data/history/ohlcv.<XAUUSD|XAGUSD|USOIL|UKOIL>.<1H|2H|4H|1D>.json` — 1H for ~2.4 years, 1D for 10 years, 2H/4H aggregated. Research input only (the launchd scanner never touches it): exchange session hours, real contract volume and a futures basis, unlike the CFD quotes and tick volume the MT5 bridge trades on. Every CFD ranking built on it says so.

## Commodities market-data contract (XAUUSD/XAGUSD/USOIL/UKOIL) — MT5 file bridge (LIVE for XAUUSD since 2026-09-10, see mt5-bridge.md)

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

- **Futures testnet (2026-09-10):** Keychain account `binance-futures-testnet`, services
  `trading-system-binance-futures-testnet-api-key` / `trading-system-binance-futures-testnet-secret-key`; keys are
  created at https://testnet.binancefuture.com and added with `security add-generic-password -a binance-futures-testnet -s <service> -w '<value>'`
  by the user, never pasted into chat. `scripts/get-secret.sh <service> binance-futures-testnet` reads them;
  `scripts/binance-futures-testnet-order.sh check` reports presence without printing values.

## No dedicated Heatmap/Liquidity knowledge-base source

Unlike Wyckoff/ICT/Footprint, there is no ingested book/course covering Heatmap/Liquidity theory in `docs/`. `HeatmapSkill`'s rules are sourced only from the master system prompt's own text (§2.4, §8). If the user adds a dedicated source later, ingest it the same way the Wyckoff book was ingested before trusting HeatmapSkill at STRICT mode.

## Instrument coverage in mock fixtures (v1)

`BTCUSDT` only, across `1D/4H/1H/15m` (market-data) and all five CoinGlass endpoints. This is enough to exercise the full pipeline end-to-end once. Add `ETHUSDT`, `SOLUSDT` fixtures the same shape when needed (both are Binance-coverable the same way as BTCUSDT). For `XAUUSD`/`XAGUSD`/`USOIL`/`UKOIL`: CoinGlass's `liquidation-heatmap`/`open-interest`/`funding` endpoints don't apply to commodities at all (crypto-derivatives-specific) — `HeatmapSkill` should report those `UNAVAILABLE`, not mocked, for these instruments; only `orderbook-heatmap` and `footprint-history` concepts could ever translate to a commodities venue, and only once a specific CFD/futures broker's real API is wired in — do not mock a CoinGlass-shaped commodities integration that doesn't exist.

## Chart refresh: three-layer read, numbers from code (2026-09-10)

**Forward ledger of the full read's Wyckoff events (2026-09-11).** Every `*-daily-full` cron, after `check-narrative.py` passes, runs `python3 scripts/event-ledger.py append --style <style>`: each event in `wyckoff.events` (Spring/Shakeout for longs, UT/UTAD for shorts, and every other label) is appended once to `data/live/events/wyckoff-events.jsonl` with the trading range and phase the read drew. `event-ledger.py measure` later scores the reversal events from stored candles (entry = close back inside the TR, stop beyond the event extreme, target = the opposite border, breakeven +1R, ICT confirmation flag) into `docs/backtests/wyckoff-events-ledger.md`. This is the only measurement of the model's own Springs/Upthrusts; code proxies live in `backtest-methods.py`.

Published report artifacts are kept current by three layers with distinct jobs. **Since 2026-09-13 there is ONE
authored style vocabulary: three horizons, one timeframe each, shared by both markets** — `scalping` 15m, `day` 1h,
`swing` 4h (`scripts/automation.py:129` (`HORIZON_TF = {"scalping": "15m"`)). The flat style names the scanner, the
model-read layer and the builder key off are *derived* from that table at `automation.py:132`
(`STYLE = {(m, HORIZON_TF[h])`) — crypto keeps the bare horizon word, cfd takes a `cfd-` prefix. **Do not restate the
name list here; read `automation.HORIZON_TF`.** Window sizes per timeframe come from `automation.SCAN_WINDOW`
(`automation.py:137` (`SCAN_WINDOW = {`)) and are project parameters, not source-derived; `scan-loop.sh` reads them
and skips a style rather than falling back to a hardcoded number. Each style is gated per market by `/automation`
(`docs/architecture/automation-config.json`, `schema_version 3`; the same file's `execution.environment` selects
`config/env.demo` or `config/env.real` for execution).
The governing rule, adopted after Haiku (anchor comparison) and Sonnet (invalidation dates) both
produced wrong numbers on 2026-09-09/10: **numbers come from code, words come from the model.**

| Layer | Owner | Cadence | Output |
|---|---|---|---|
| 1. Đánh giá sơ bộ (scanner) | `scripts/ict-scan.py`, run by the launchd agent `com.tyme.trading.scanner` via `scripts/scan-loop.sh` | `scalping` + `cfd-scalping` (15m) at :01/:16/:31/:46; `day` + `cfd-day` (1H) at :02 every hour; `swing` + `cfd-swing` (4H) at :03 of every 4th hour, which is also when the `1D`/`1W` **context** candles are fetched — context rungs are drawn, never scanned (`scan-loop.sh:106-110` (`run_style 15m scalping`)) | `data/live/prelim/<style>.<SYM>.html` (head + **facts table**), `<style>.facts.json` (incl. the `context` block of the higher-timeframe style, `scripts/htf_context.py`), `<style>.meta.json`, `data/live/scan-state.<style>.json`; NEW sweep / ERL touch / MSS appended to `data/live/events.jsonl` |
| 2. Đánh giá cục bộ (Sonnet local read) | Sonnet agent fed by `scripts/local-eval-brief.py <style>`; validated by `scripts/check-model-prose.py <style>` (numbers + method purity) | Minimum gap per style, enforced by `scripts/model-read.sh:29` (`MODEL_READ_INTERVAL=900`): `scalping`/`cfd-scalping` 15 min, `day`/`cfd-day` 1 h, `swing`/`cfd-swing` 4 h. The `scalping` local read additionally skips when no new scalping event landed in `events.jsonl` since the last read (`scripts/scalping-events-since.py`) — a guard written when `scalping` meant 1m and kept deliberately after the 2026-09-13 rename | `data/live/prelim/<style>.<SYM>.model.html` — per-method blocks `m-wyckoff` / `m-ict` (/ `m-footprint` / `m-heatmap` when CoinGlass is live) / `m-synth`, 2–4 cited sentences each, quoting only numbers present in facts.json; the synthesis block is the only place both methods meet and must open with the higher-timeframe context ("Bối cảnh <tf>: …", giảm khung — SYSTEM-DESIGN §15.2) |
| 3. Đánh giá toàn diện (full analysis) | Sonnet agent, writes the structured narrative `data/live/narrative/<style>.json` (schema `docs/architecture/schemas/narrative.schema.json`; validated by `scripts/check-narrative.py`) | once per day per chart after the UTC daily close (07:30 / 07:40 / 07:50 Asia/Saigon) and on a structure invalidation (scanner verdict `PHÁ DƯỚI` / `PHÁ TRÊN` / `PHÁ CẤU TRÚC`) | per-method Wyckoff / ICT (/ Footprint / Heatmap) texts, Wyckoff chart events by candle time, timeline, synthesis with invalidation owner, and a `context` read of the HTF overview window; `scalping` never publishes (the tick renders it); `day`/`swing` and their `cfd-` pairs build + publish; **must also rewrite `data/live/anchors.<style>.json`** (every level tagged `method` + `short`) |

- **Anchors** (`data/live/anchors.<style>.json`): the last full analysis names the structural levels (e.g. `sweep_low`, `range_top`, `LPS_old`; swing `spring_low`) with role and time, plus a verdict rule (`range` between support and resistance, or `floor`). The scanner computes, per level, close above/below, distance %, the **first completed close beyond it after the anchor time** (invalidation candle) and the extreme since; the verdict is evaluated on the last **completed** candle, never the forming one. Verified 2026-09-10 against hand-computed values (first 15m close below the 9/9 LPS: BTC 15:00Z, ETH 15:15Z, SOL 15:00Z).
- **Setup candidate**: when the chain sweep → MSS (same direction) → FVG exists inside the last `max(12, 6×recent)` bars, the scanner emits entry (FVG edge), stop (sweep extreme), target (nearest unswept pool, else window ERL) and R. Models may only quote these; `check-model-prose.py` rejects a `SETUP TIỀM NĂNG` verdict without a complete setup and flags any ≥3-digit number not present in facts.
- **Page rendering (2026-09-11)**: `scripts/build-artifact.py <style> --out FILE` renders the whole page from code — working window with volume, an HTF context window (`STYLES[...].ctx`, shaded where the working window sits; its Wyckoff annotations come from the narrative of the style that owns that window, `CTX_REUSE`), layer 1 split per method from facts.json, layers 2/3 per-method blocks, synthesis column, event timeline, per-lane glossary. The page has one chart lane per method (Wyckoff = price + volume + TR/phases/events; ICT = price-only engine; Footprint/Heatmap = status panel until CoinGlass is live). `patch-arrays.py`, `inject-prelim.py`, `select-base.py` were retired 2026-09-11 and are no longer in the tree. Every block carries its own data timestamp so staleness is visible.
- **Publish ticks** (Haiku, local cron, scalping every 3 min): no fetching or scanning of their own — `build-artifact.py scalping --snapshot-dir` (snapshots the candle files it used), Artifact read, publish. `day`, `swing` and their `cfd-` pairs build + publish as part of their Sonnet local tick. A build exits 2 and refuses to render when any per-method block leaks the other method's vocabulary (`scripts/method_purity.py`).
- **Event handling**: the Claude session watches `data/live/events.jsonl` with the Monitor tool (`tail -F`), not by polling; each new line is a sweep / ERL / MSS already deduplicated by the scanner state. Alerts go out as PushNotification (currently disabled in `/config`, so they surface in the session only).
- **Single writer**: since the launchd agent owns `data/live/market-data`, `data/live/prelim` and the scan state, agents no longer race on those files (the 2–3 min chart-vs-meta-strip lag seen on 2026-09-10 came from concurrent agents re-fetching the same files).
- **Single-publisher rule for scalping** (unchanged in spirit): the full analysis writes `data/live/narrative/scalping.json` atomically; the next publish tick renders and publishes it (no marker needed — the builder reads whatever is current). Never run two full analyses of one chart concurrently — the 2026-09-10 outage produced five overlapping runs that overwrote each other's hand-off file with older data.
- **Cloud routines** remain disabled: the cloud sandbox's egress proxy refuses `api.binance.com:443`; re-enable only if that host is allow-listed. Data timestamps in the artifacts are the fetch time of api.binance.com klines (mainnet public), not testnet.
- **Headless model layer (2026-09-11, night).** The layer-2 local reads and the layer-3 daily full analysis no longer run as session crons: `scripts/scan-loop.sh` starts `scripts/model-read.sh <style> local|full` right after each scanner pass — a detached `claude -p` (Sonnet, `--allowedTools` limited to the analysis scripts and the files that layer owns, no Artifact tool) per style, in parallel, with per-style minimum intervals (`scalping`/`cfd-scalping` 15 min, `day`/`cfd-day` 1 h, `swing`/`cfd-swing` 4 h, `full` once a day 07:30–07:59Z) and a lock. Prompts in `integrations/headless/` — **only four exist today**, the `scalping-*` and `cfd-scalping-*` local/full pair; `day`, `swing`, `cfd-day` and `cfd-swing` have no prompt file, so `model-read.sh` exits 2 for them and no local read runs (`scan-loop.sh:111` (`only these two have a prompt pair`)). Logs and run dirs in `data/live/model-reads/`. They run whether or not a Claude Code session is open. The session keeps only `publish-tick` (every 5 min: `scripts/publish-plan.py` → build → Artifact read/publish → mark) and `journal-publish`; artifact URLs in `docs/architecture/artifacts.json`.
- Artifact publishes happen in the cron turn itself (main session), never in a subagent — a subagent's `Artifact read` does not satisfy the publish check, which is why the 2026-09-11 crons published nothing until the templates were rewritten. Sonnet subagents only write model blocks and run checkers; they must not open script/knowledge sources (rate limits).
- Local crons are session-scoped (die with the session, expire after 7 days); the launchd scanner and the pilot loop are the only pieces that survive a session restart. Since 2026-09-10 the cron prompts are versioned as templates in `integrations/crons/*.md` and `/automation on|demo|real` re-creates them in the current session via `scripts/cron-templates.py` (`/automation off` deletes them) — see `.claude/commands/automation.md` steps 7–8. A resumed subagent has its Artifact publish blocked by the permission classifier — cron prompts always dispatch a fresh agent.
