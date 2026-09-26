# Plan: real-time Heatmap trading (Bookmap) and a seconds-capable decision path

- **Date:** 2026-09-26 · **Status:** DRAFT v3. Revised after two adversarial review rounds:
  - Round 1 (C1-C5, H1-H7, M1-M6) was addressed in v2.
  - Round 2 found six partial fixes and ten new problems (N1-N10); v3 addresses them, mainly through §1.8 and the
    H1 changes.
  - Awaiting the owner's Heatmap/Bookmap source material for H3.
- **Governing decisions:** ADR 0007 (build order; methodologies extended, never altered), CLAUDE.md §4, §6-§8,
  §10, §20, §23, §31, §36-§40, §47, §51-§53, §57. A new ADR 0008 (Bookmap integration and Heatmap scope) is
  required before H2 merges.
- **Owner priority (2026-09-26):** analysis accuracy first. A fast decision on a wrong analysis is worthless, so
  no stage may trade correctness for speed.

## 0. Grounded facts (Bookmap Level1Api / SimplifiedApiWrapper 7.6.0, javadoc in `C:\Program Files\Bookmap\lib`)

| Fact | Javadoc |
|---|---|
| A module is a class annotated `@Layer1SimpleAttachable` + `@Layer1ApiVersion(VERSION3)`, with an optional `@Layer1StrategyName`, implementing `CustomModule.initialize(alias, InstrumentInfo, Api, InitialState)` / `stop()`. With no version value, VERSION0 is assumed. | `simplified/CustomModule`, `annotations/Layer1ApiVersion`, `Layer1ApiVersionValue` |
| `DepthDataListener.onDepth(boolean isBid, int price, int size)`: the price is a **level number**, and price = level × `pips` | `simplified/DepthDataListener`, `data/InstrumentInfo#pips` |
| `TradeDataListener.onTrade(double price, int size, TradeInfo)`: the price is a (possibly fractional) level number in the same units as depth; `TradeInfo.isBidAggressor` gives the aggressor side | `Layer1ApiDataListener#onTrade`, `data/TradeInfo` |
| Sizes are integers premultiplied by `InstrumentInfo.sizeMultiplier` | `data/InstrumentInfo#sizeMultiplier` |
| `TimeListener.onTimestamp(long t)` is **Bookmap's clock** ("time of the next event"), which can distort when the consumer is slow. It is **not** an exchange timestamp. The Simplified API exposes no exchange time and no sequence id. | `simplified/TimeListener`, `Layer1ApiAdminProvider#getCurrentTime` |
| `InstrumentInfo`: `pips`, `sizeMultiplier`, `dataDelay` (`UNKNOWN_DELAY` = 1), `isFullDepth`, `isCrypto`, `recordingTag`, `isApiProtected` | `data/InstrumentInfo`, `constant-values` |
| An API-protected instrument blocks unsigned add-ons (`@UnrestrictedData` is trusted only when the module is signed) | `annotations/UnrestrictedData` |
| Historical, backfill and replay data reach the same listeners (`HistoricalDataListener`, `BackfilledDataListener`, `HistoricalModeListener.onRealtimeStart`, replay providers) | `simplified/*`, `layer0/replay` |
| Connection loss is signalled only in the Level1 admin API (`Layer1ApiAdminListener.onConnectionLost/Restored`), not in the Simplified API | `Layer1ApiAdminListener` |
| The `Api` handed to every module exposes `sendOrder`/`updateOrder`/`getProvider` | `simplified/Api` |
| Bookmap ships a Java 21 runtime without a compiler; building needs a JDK 21 | `C:\Program Files\Bookmap\jre` |

**To verify in H1, never assume:** whether pips equals the exchange tick for the owner's feed, whether
`isFullDepth` is set, what `onSnapshotEnd` means, whether a mark price is available, whether the module
auto-re-enables after a restart, and whether the admin listener is reachable from the Simplified wrapper.

## 1. Architecture principles

0. **Heatmap is not a candle model (owner, 2026-09-26, with a Bookmap screenshot).**
   - Heatmap trades a continuous **time × price** picture: resting liquidity per price level over time (the heat
     map), executed trades as bubbles sized by volume and coloured by aggressor, the current order book (COB), and
     the session volume profile (SVP).
   - Recording, features, the H5 research engine and the H4 decision path for Heatmap are therefore
     **event-driven on raw book and trade events**. They never aggregate into OHLC bars, and no Heatmap decision
     waits for a bar close.
   - **Footprint is the only order-flow methodology traded on candles**: trades → aggressor classification →
     per-bar, per-price bid/ask aggregation (CLAUDE.md §22). It is built from the same recorded trades.

1. **Recording first, and read-only.** The book history cannot be downloaded later, so recording starts as soon as
   H1 passes its Security review. It is not gated on audit round 4b or on the owner's material.
2. **One feature implementation.** Heatmap features and analytics are computed once, in Python, from normalized
   events. The same code runs live and on replayed recordings (§37). The Java add-on only captures and
   forwards raw events; it computes no trading features.
3. **PIT timing (§8).** `availableTime` = the moment the consuming Python process received the record, stamped
   at every hop (add-on receive, send, Python receive). `bookmapTime` is kept as a separately named field and is
   never called an exchange event time. Replay makes decisions on the recorded Python arrival times, so the
   backtest carries the real transport latency. Live use is refused when `dataDelay != 0`, when it equals
   `UNKNOWN_DELAY`, or when `recordingTag` is set. Those states are UNKNOWN/INVALID and entry is blocked.
4. **LIVE only.** Every record carries `mode` ∈ {HISTORICAL, BACKFILL, REPLAY, LIVE}, with the live boundary taken
   from `onRealtimeStart`. The decision process rejects everything except LIVE. |bookmapTime − wall clock| beyond
   a threshold marks the stream INVALID. An adversarial test proves that replay mode cannot produce an entry.
5. **A book is valid only when proven valid.**
   - `onConnectionLost` marks the book INVALID until a snapshot completes after the restore.
   - Structural checks (crossed/locked book, trade with no book at the touch) mark it INVALID.
   - A periodic cross-check against a Binance REST depth snapshot (top N levels, via `pips`) catches silent
     divergence.
   - The add-on's own monotonic counter detects only add-on-internal loss, and this limit is stated wherever the
     counter is used.
   - Completeness is asserted only inside a declared depth window (±N ticks). Beyond it the book is PARTIAL and
     cannot feed REQUIRED analysis.
6. **Venue honesty (§4, §23).** Bookmap shows the **mainnet** book. The Binance futures **testnet** is a different
   book, so testnet validates plumbing and safety only, never fills or edge. The Heatmap execution model assumes
   the book it reads. A venue order-book heatmap and CoinGlass's aggregated heatmap are separate, separately
   labelled evidence (§23).
7. **Speed from structure, never from skipping work.** A long-running, event-driven process holds its state in
   memory. It does not spawn a script per event (the current `strategy-runner.py` shells out per exchange call
   and cannot be the seconds path). It still waits for every REQUIRED_FOR_DECISION input (§36). Latency uses the
   existing `scripts/latency.py` and `docs/architecture/latency-model.json` (§40), not a second recorder.
   - **Estimated budget (to be replaced by measurements):** feed hop <5 ms; features and rules ~1-10 ms; order to
     exchange ~50-300 ms.
   - **Out of scope:** millisecond HFT.
8. **Python owns everything outside Bookmap, from day 1 (resolves N1, N2, N7).**
   - **Add-on (Java):** capture + bounded queue + forward, and nothing else. It makes no network calls and writes no
     files.
   - **Recorder (Python, long-running):** owns the named pipe and sets its ACL (Java has no native named-pipe
     server, so Python must be the server — to be confirmed in the Security review). It stamps the Python arrival
     time, writes the recording files, and makes all outbound calls (REST depth cross-check, `aggTrades`
     reconciliation, `exchangeInfo` tick size, Binance server-time clock offset).
   - **Consequence:** every recording carries the Python arrival time that §1.3's availableTime needs, including
     the very first one.
   - Later, the H4 live consumer reads the same stream. The recorder's own receive path is the one tested in H1.
9. **The clock-drift check (§1.4) runs in LIVE mode only**, and is defined against the recorded lag metric
   (Python arrival − add-on receive), so legitimate backpressure is measured rather than misread as clock
   error (N8).

## 2. Stages

Each stage ends with a review.

### H1 — Recorder add-on (read-only). Runs in parallel with audit round 4b, before any owner material.
- **Security review first** (new vendor = trust boundary):
  - The add-on must never call `sendOrder` or `updateOrder`, and is never annotated `@Layer1TradingStrategy`.
  - `getProvider` is allowed at exactly **one call site**: a single audited class whose only action is registering
    the connection (admin) listener. The build-time check enforces both the single call site and the absence of
    the order calls (N7).
  - **If the admin listener turns out to be unreachable from the Simplified wrapper**, the add-on moves to the full
    Level1 API (`@Layer1Attachable`) for connection events. Until that is solved, recordings carry
    `connection_state=UNKNOWN`: acceptable for research, and a blocker for H4 live use.
  - The add-on makes no outbound network calls. Only the Python recorder does (§1.8).
  - Bookmap's own exchange connection uses no API keys, or read-only keys.
  - The add-on jar's hash is pinned and checked at load.
- **Capture:** depth, trades (with aggressor), Bookmap time, mode, connection events, and `InstrumentInfo`
  (including `pips`, `sizeMultiplier`, `dataDelay`, `isFullDepth`, `recordingTag`, `isApiProtected`) plus the
  Bookmap version.
- **Forwarding and writing (split per §1.8):**
  - In the add-on, callbacks go into a bounded queue drained by a forwarder thread, so Bookmap's callback thread
    never blocks. The forwarder sends to the Python recorder's pipe.
  - The Python recorder writes the files. If the recorder is down, the add-on queue overflows and a gap is marked.
  - An overflow is recorded as a gap and marks the stream INVALID. Nothing is dropped silently.
  - Queue depth and lag are recorded as quality inputs.
  - A timer-driven heartbeat runs even when the market is quiet.
- **Format:**
  - Each file has a schema version and a header: instrument info, add-on git SHA, Bookmap version, and the
    clock offset against Binance server time.
  - Each hourly file starts with a book checkpoint, so it replays on its own.
  - Every record carries a length and CRC, so a crash truncates only the tail.
  - A run manifest (files, hashes, gaps, modes, time range) is the §10 dataset-snapshot id.
- **Storage:**
  - A **git-ignored** directory outside tracked `data/`, with a test that it stays ignored.
  - A storage estimate, a retention policy and an off-disk backup, because the data is irreplaceable.
- **First hour gate (N3):**
  - Compare `pips` with the exchange tick from `exchangeInfo`, and `sizeMultiplier` with the step size.
  - A mismatch aborts recording.
  - The exchange tick is written into **every** file header, because Binance can change `tickSize`.
- **Pre-registration at H1 start, not at H5 (N4):**
  - The in-sample / holdout calendar for all future recorded weeks is entered in the research ledger before the
    first recording.
  - Automated quality metrics do not expose a week. Any human or feature-design look at a week's market content
    does, and is logged as exposure.
- **Numeric tolerances, fixed in the H1 design review before coding (N2):**
  - Levels compared.
  - Time-alignment window (the book has no sequence ids, so REST snapshots align by time only).
  - Size tolerance per level.
  - Failure thresholds.
- **Exit:**
  - 24 h of continuous LIVE recording.
  - The book reconciles with Binance REST snapshots within the pre-set numeric tolerance.
  - Trades reconcile with Binance `aggTrades` (downloadable).
  - Every connection loss is visible in the manifest.
  - Bookmap CPU/RAM overhead is measured.
  - Every "to verify" fact in §0 is answered.
  - A lossless record→replay round trip is a necessary check, not the correctness exit.

### H2 — `bookmap_bridge` provider, normalization and ADR 0008
- Normalization: price = level × `pips`, size = size / `sizeMultiplier`. `pips` must equal the exchange tick from
  `exchangeInfo` or the stream is refused. `pips` is part of the dataset identity, because recordings made with
  different `pips` are not comparable.
- Capabilities use existing vocabulary ids only (`orderbook_depth`, `trades_raw`; §6). No other capability is
  claimed.
- **ADR 0008** records how Bookmap relates to the existing `heatmap` dimension (`docs/architecture/methods.json`,
  which today means CoinGlass aggregated liquidation/orderbook heatmaps) and to Footprint, which `trades_raw`
  makes live-capable. This is a scope decision, not a silent swap of data source (ADR 0007).
- Quality states FRESH/STALE/MISSING/PARTIAL/INVALID/UNKNOWN are driven by §1 items 3-5.
- The feed hop to Python is authenticated: a Windows named pipe with an ACL, or a per-session HMAC key in an
  ACL'd file. A bare 127.0.0.1 port is not enough, because any local process could bind it while Bookmap is
  down. Every message is schema-validated (size, NaN, types).

### H3 — Heatmap methodology from the owner's sources (blocks any Heatmap trading)
- Ingest the material into `knowledge/heatmap/`, indexed in `knowledge/INDEX.md`.
- Derive observations, setups, invalidation and expectations **only** from those sources, with citations
  (ADR 0007, §13). Unquantified values are project-defined research parameters.
- Features are designed here, in Python, as the single implementation from §1.2.
- Until H3 merges, Bookmap data is VISUALIZATION_ONLY / RESEARCH_ONLY.

### H5 — Research on recordings (the accuracy gate). Runs before any live seconds path.
- **Blocked on ADR 0007 stage (c)** (experiment ledger and validation gates) being merged.
- **Pre-registered holdout calendar:** recorded weeks are assigned to in-sample or holdout **before** anyone looks
  at them, entered in the research ledger. A first look at any other week exposes it.
- **Fill model (project-defined, with sensitivity runs):**
  - Back-of-queue entry; the queue is decremented only by trades at that level, not by cancels.
  - Order arrival = decision availableTime + sampled measured latency (p99 for stress).
  - Taker fees, spread and order-rate limits are included.
- **Stops:** live stops use `workingType=MARK_PRICE`. There are two options:
  - The mark price is recorded from a declared source. A mark-price capability must first be added to
    `docs/architecture/providers.json` (§6, N9).
  - Or the Heatmap Trading System uses contract-price stops as an explicit, versioned choice (§47).
- **Holdout:** the calendar comes from the H1 pre-registration. H5 only reads it.
- **Exit:** a candidate is net-positive after costs on untouched holdout weeks, with its sample size shown and a
  minimum calendar span and regime coverage. At seconds scale most candidates are expected to die here, which is
  the purpose of the stage.

### H4 — Seconds-capable live path (only after H5 has a surviving candidate; §57)
- **One set of gates, two drivers (N5):** the shared gate functions (data quality, event risk, session, account,
  risk, final eligibility) are extracted so that the 15m loop and the event-driven path call the **same** code.
  Both must pass a conformance test generated from `docs/architecture/decision-order.json`. There is no second
  implementation of the §36 ordering. The existing
  15m/1H/4H path is **not** refactored now. It migrates later only with byte-identical stability rows as the
  acceptance test (ADR 0007 stage b).
- Exchange calls go through an in-process client, not a bash spawn per order.
- The news/event calendar is preloaded as a point-in-time snapshot, so blackout checks run at seconds cadence
  (§28-§29).
- **Failure handling:**
  - A timer heartbeat detects silence.
  - `SUBSCRIPTION_LIMIT`, license expiry, `SIMULTANEOUS_LOGIN`/`FATAL` disconnects and halted markets stop entries.
  - The clock offset against Binance server time is checked periodically; beyond a threshold, entries stop.
  - When the feed goes STALE, open positions rely on exchange-resident stops/targets (§31), never on the feed.
- **Seconds rule for existing methodologies:** a Trading System runs on a seconds timeframe only when its
  methodology's source defines behaviour at that scale. Wyckoff/ICT keep their sourced timeframes. A shorter
  timeframe is a new Trading System version (§47).

### H6 — Pilot, then human decision
- **Paper execution against the live mainnet book**, using the H5 fill model. This is the edge test.
- **In parallel, testnet orders for mechanics only** (placement, stops, cancels, rate limits).
- Latency SLOs are enforced: p99 over budget or a non-FRESH feed stops entries.
- Paper results are compared with a replay of the same recorded period. A divergence beyond the fill model's
  tolerance is a defect. This tests **determinism only**, not realism (N6).
- **Known residual risk:**
  - The fill model is never validated against real fills: testnet cannot validate them (§1.6) and mainnet is
    excluded.
  - The only real validation is a separate, human-approved, minimal mainnet order study under §51.
  - Until then, every result is labelled "fill model unvalidated".
- **The first Heatmap Trading System is registered as v1** in `docs/architecture/trading-systems.json` when it is
  created, with its dependencies classified (§35, §47).
- The 1% risk ceiling, news blocks and account rules are unchanged. Any real-money use is a separate, explicit
  human decision (§51).

## 3. Ordering

```
H1 recorder (now, parallel to round 4b) ──> H2 provider + ADR 0008 ──┐
H3 methodology (when the owner's material arrives) ──────────────────┼──> H5 research ──> H4 live path ──> H6 pilot
ADR 0007 stage (c) ledger + gates (after the speed round) ───────────┘
```
Three independent tracks join at H5 (N10). H5 cannot start until all three are merged.

## 4. What the owner provides

1. Bookmap connection details: which exchange/feed, and whether it uses API keys. Read-only or no keys are
   preferred.
2. Permission to install JDK 21 (`winget install Microsoft.OpenJDK.21`) to build the add-on.
3. Heatmap and Bookmap trading material for H3.
