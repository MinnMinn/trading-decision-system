---
description: Full institutional trading analysis pipeline (Data Validation through Trade Plan) for one instrument. Analysis only — never executes.
argument-hint: <INSTRUMENT> [MODE=NORMAL|ENHANCED|STRICT] [mock]
---

**Model gate (SYSTEM-DESIGN.md §14).** This command reasons. If you are running as Haiku, do not execute any step below in this session: dispatch one `general-purpose` subagent with `model: sonnet` to run this command's full procedure with the same `$ARGUMENTS`, then relay its output verbatim. Haiku displays; it never analyzes, scores or judges.

Run the full 12-step Decision Pipeline (master system prompt §12) for the instrument given in `$ARGUMENTS`. This command IS the DecisionAgent orchestration layer referenced in `docs/architecture/SYSTEM-DESIGN.md` §5/§6 — you (the main session) perform the synthesis steps directly; you dispatch structure-agent, flow-agent, liquidity-agent, and risk-agent for their respective read-only analysis passes.

**Refuse immediately, before any analysis, if:** the instrument isn't in {BTCUSDT, ETHUSDT, SOLUSDT, XAUUSD, XAGUSD, USOIL, UKOIL}, or is any Forex pair — cite the hard rule and stop.

## Steps

1. **Data Validation.**
   - **Crypto instruments (BTCUSDT/ETHUSDT/SOLUSDT):** unless `mock` is in `$ARGUMENTS`, run `scripts/fetch-binance-klines.sh <SYMBOL> <TIMEFRAME>` for each needed timeframe (1D/4H/1H/15m). Exit 0 with `_source: "binance_public_rest_live"` in the output file → `crypto_market_data: AVAILABLE`, read from `data/live/market-data/`. Any failure → `crypto_market_data: UNAVAILABLE`, do not silently fall back to a stale live file or to mock without saying so.
   - **Commodities (XAUUSD/XAGUSD/USOIL/UKOIL):** if an MT5 bridge file exists under `data/live/mt5-bridge/` and is fresh (per `docs/architecture/mt5-bridge.md`'s staleness rule), report `commodities_market_data: AVAILABLE` and read from it. Otherwise `UNAVAILABLE` — never invent commodities data.
   - **If `mock` is in `$ARGUMENTS`**, or a live fetch failed and the user wants a rehearsal anyway, use `mock/market-data/*.json` and `mock/coinglass/*.json` fixtures instead and set `rehearsal_mode: true` for the whole run.
   - Emit the `DataValidationStatus` block (`docs/architecture/schemas/data-validation-status.schema.json`) — every source AVAILABLE/STALE/UNAVAILABLE/MOCK, explicitly. If `rehearsal_mode` is true, print the banner: `⚠ REHEARSAL MODE — mock data in use, not a live signal.` at the very top of your final output, and again just before the Final Verdict.

2. **Event Risk.** Check `docs/architecture/event-calendar.md` for today's date. Report HIGH/MODERATE/LOW/UNKNOWN — UNKNOWN if the calendar has no covering entry, not LOW.

3. **Methodology Mode — lock it now.** Use the mode from `$ARGUMENTS` if given, else default NORMAL, else ask the user if genuinely ambiguous. Record it and do not change it later in this run regardless of how the score comes out (mode-lock rule, `SYSTEM-DESIGN.md` §6.2).

4. **HTF Context + Setup Detection.** Read Daily/4H data yourself (via structure-agent's forthcoming read, or a quick own pass) to classify Market Regime (TRENDING/RANGING/TRANSITIONAL/UNCLEAR) and name the candidate Setup Type (Spring, Upthrust, Trend Continuation, etc. — master spec §14). If Regime is UNCLEAR and the setup depends on ranging behavior, flag this now.

5. **Dispatch the read-only agents** (single message, parallel Agent tool calls where the harness supports it).
   **First read `docs/architecture/automation-config.json` if it exists** (`schema_version 2`; missing file = unconfigured = dispatch everything, exactly as before this switch existed). It gates *which* agents are dispatched:
   - **structure-agent** — always dispatched (Wyckoff + ICT): instrument, timeframes, exchange market-data path(s) (real or mock), the candidate setup location.
   - **flow-agent** (Footprint) — **do NOT dispatch** when the instrument is a CFD (XAUUSD/XAGUSD/USOIL/UKOIL — `markets.cfd` has no `footprint` key at all, there is no CoinGlass source for commodities, `SYSTEM-DESIGN.md` §12 item 3), or when `markets.crypto.dimensions.footprint` is `false`. Otherwise: instrument, the specific anchor candle/bar structure-agent identifies, CoinGlass footprint data path.
   - **liquidity-agent** (Heatmap) — **do NOT dispatch** when the instrument is a CFD (same reason), or when `markets.crypto.dimensions.heatmap` is `false`. Otherwise: instrument, CoinGlass heatmap data paths.
   Wait for all dispatched returns before scoring. **State in your output which agents were skipped and why** (name the flag or the structural limit), and remind the reader that a skipped dimension lowers `engaged_count`, which can fall below the locked mode's minimum (NORMAL ≥2, ENHANCED/STRICT ≥3, §6.1/§6.2) and force NO TRADE on count alone — a configuration outcome, not a market read.

6. **Independent-Confluence Check.** For each of the 4 dimensions, determine `eligible` (data AVAILABLE, not MOCK/STALE/UNAVAILABLE, and actually analyzed) and `engaged_count`. Compare against the locked mode's minimum (NORMAL≥2, ENHANCED≥3, STRICT≥3-explicitly-selected). If unmet: **verdict is NO TRADE**, skip to step 9.

7. **Contradiction Analysis.** Run this against **every** dimension whose data was AVAILABLE, not only the engaged ones (anti-cherry-picking rule). List bullish evidence, bearish evidence, and an explicit resolution for each contradiction found.

8. **Confluence Score.** Compute per `docs/architecture/SYSTEM-DESIGN.md` §6.2: `raw_pct = (sum of engaged-dimension points) / (engaged_count × 25) × 100`, subtract the Contradiction Penalty (percentage points), floor at 0 → `final_score`. Compare to the mode threshold (70/80/85) → `threshold_met`. `verdict = TRADE` only if `threshold_met` AND `dimension_count_met` AND no blocking HIGH event-risk-window contradiction; otherwise `WAIT` (close, salvageable with more confirmation) or `NO_TRADE` (structurally invalid).

9. **If verdict could be TRADE:** dispatch **risk-agent** with the candidate entry/stop/targets. If RiskAgent returns any hard-check FAIL, downgrade the verdict to NO_TRADE and say exactly which check failed — do not soften this.

10. **Trade Plan + Final Verdict.** Produce the full Decision Output per master spec §23 (Market State → HTF Context → Setup → Methodology Evidence → Independent Confluence → Confluence Score → Trade Decision → Invalidation & Management → Final Verdict).

11. **Journal.** Invoke journal-skill to write `trades/<id>.md` for any TRADE or WAIT verdict (NO_TRADE calls are logged too, but may be terser — still worth recording for later pattern review). Regenerate `trades/index.jsonl`.

12. **Never execute.** End with: "Analysis only. Run `/execute` for a manual execution ticket — no trade has been placed."
