---
description: Full institutional trading analysis pipeline (Data Validation through Trade Plan) for one instrument. Analysis only — never executes.
argument-hint: <INSTRUMENT> [MODE=NORMAL|ENHANCED|STRICT|SOLO] [mock]
---

**Model gate (SYSTEM-DESIGN.md §14).** This command reasons. If you are running as Haiku, do not execute any step below in this session: dispatch one `general-purpose` subagent with `model: sonnet` to run this command's full procedure with the same `$ARGUMENTS`, then relay its output verbatim. Haiku displays; it never analyzes, scores or judges.

Run the full 12-step Decision Pipeline (master system prompt §12) for the instrument given in `$ARGUMENTS`. This command IS the DecisionAgent orchestration layer referenced in `docs/architecture/SYSTEM-DESIGN.md` §5/§6 — you (the main session) perform the synthesis steps directly; you dispatch structure-agent, flow-agent, liquidity-agent, and risk-agent for their respective read-only analysis passes.

**Refuse immediately, before any analysis, if:** the instrument is not on the `analysis` list of `docs/architecture/instruments.json` (read the file; do not trust a remembered list) — cite the hard rule and stop. The blanket Forex prohibition was lifted 2026-09-17, so a currency pair is refused, or not, on exactly that ground and no other.

## Steps

1. **Data Validation.**
   - **Crypto instruments** (the `crypto.analysis` entries of `docs/architecture/instruments.json`)**:** unless `mock` is in `$ARGUMENTS`, run `scripts/fetch-binance-klines.sh <SYMBOL> <TIMEFRAME>` for each needed timeframe (1D/4H/1H/15m). Exit 0 with `_source: "binance_public_rest_live"` in the output file → `crypto_market_data: AVAILABLE`, read from `data/live/market-data/`. Any failure → `crypto_market_data: UNAVAILABLE`, do not silently fall back to a stale live file or to mock without saying so.
   - **Commodities (XAUUSD/XAGUSD/USOIL/UKOIL):** if an MT5 bridge file exists under `data/live/mt5-bridge/` and is fresh (per `docs/architecture/mt5-bridge.md`'s staleness rule), report `commodities_market_data: AVAILABLE` and read from it. Otherwise `UNAVAILABLE` — never invent commodities data.
   - **If `mock` is in `$ARGUMENTS`**, or a live fetch failed and the user wants a rehearsal anyway, use `mock/market-data/*.json` and `mock/coinglass/*.json` fixtures instead and set `rehearsal_mode: true` for the whole run.
   - Emit the `DataValidationStatus` block (`docs/architecture/schemas/data-validation-status.schema.json`) — every source AVAILABLE/STALE/UNAVAILABLE/MOCK, explicitly. If `rehearsal_mode` is true, print the banner: `⚠ REHEARSAL MODE — mock data in use, not a live signal.` at the very top of your final output, and again just before the Final Verdict.

2. **Event Risk.** Run `python3 -c "import sys;sys.path.insert(0,'scripts');import event_risk as ER;print(ER.state('<SYMBOL>'))"` — do NOT read the calendar by eye. It answers CLEAR / BLOCKED / UNAVAILABLE against `docs/architecture/event-calendar.json`, per instrument (CLAUDE.md §26 — an EIA release does not reach BTC), point-in-time (§28), with overlapping windows unioned (§30). Report the impact level in the spec's own vocabulary: **HIGH / MEDIUM / LOW / UNKNOWN** — UNKNOWN when the calendar has no covering entry, never LOW (§25). UNAVAILABLE means the calendar is missing, stale or unparseable: that is the configured fail-safe (§32, default BLOCK ENTRY), not a clean bill of health.

3. **Methodology Mode — lock it now.** Run `python3 scripts/methods.py --dispatch-plan <INSTRUMENT>` now (you will reuse this exact output at step 5 — no need to run it twice) and read its `mode:` line. That mode comes from the **preset's own `mode` field** in `docs/architecture/methods.json` (SOLO for the two single-dimension presets, NORMAL otherwise) — it is a function of the preset the user selected in `/automation`, never of how many dimensions turn out to be live-available once you reach step 6.
   - If `$ARGUMENTS` gives an explicit `MODE=`: `SOLO` is **only** legal if the printed mode is already SOLO (i.e. the preset itself names exactly one dimension) — refuse and ask the user to re-pick if they pass `MODE=SOLO` under a multi-dimension preset; that is precisely the after-the-fact downgrade the mode-lock rule forbids. `NORMAL`/`ENHANCED`/`STRICT` may still be explicitly requested regardless of preset, exactly as before (a preset that can't reach the requested minimum will simply report NO TRADE on count at step 6, same as today).
   - If `$ARGUMENTS` gives no mode: default to the printed mode (so a single-dimension preset defaults to SOLO instead of an NORMAL default that could never pass).
   - Record whichever mode results and do **not** change it later in this run regardless of how the score comes out, and regardless of `engaged_count` turning out lower at step 6 than it was at this step (mode-lock rule, `SYSTEM-DESIGN.md` §6.2 — this is exactly the rule that keeps a degraded multi-dimension preset from silently becoming SOLO).

4. **HTF Context + Setup Detection.** Read Daily/4H data yourself (via structure-agent's forthcoming read, or a quick own pass) to classify Market Regime (TRENDING/RANGING/TRANSITIONAL/UNCLEAR) and name the candidate Setup Type (Spring, Upthrust, Trend Continuation, etc. — master spec §14). If Regime is UNCLEAR and the setup depends on ranging behavior, flag this now.

5. **Dispatch the read-only agents** (single message, parallel Agent tool calls where the harness supports it).
   **Reuse the `python3 scripts/methods.py --dispatch-plan <INSTRUMENT>` output from step 3** (same instrument,
   same config, so it is identical — do not run it again). It prints the method preset in force, the locked
   `mode:` (and its minimum/threshold), a `DISPATCH:` line naming exactly which agents to dispatch, and one
   `SKIP <dimension>:` line per skipped dimension with the reason. Dispatch exactly what `DISPATCH:` names and
   nothing else; pass each agent the instrument, the timeframes, the data-source paths, and (for flow-agent) the
   anchor candle structure-agent identified. **Reproduce every `SKIP` line verbatim in your output**, and remind
   the reader that a skipped dimension lowers `engaged_count`, which can fall below the locked mode's minimum
   (SOLO ≥1, NORMAL ≥2, ENHANCED/STRICT ≥3, §6.1/§6.2) and force NO TRADE on count alone — a configuration
   outcome, not a market read. Do not maintain a list of agents in this file; the registry
   (`docs/architecture/methods.json`) is the source, so adding a dimension needs no edit here.

6. **Independent-Confluence Check.** For each of the 4 dimensions, determine `eligible` — true only if the dimension is **engaged by the active preset** (it has no `SKIP` line in step 5's dispatch plan) AND its data is AVAILABLE (not MOCK/STALE/UNAVAILABLE). A lane that is analysed but not traded (CLAUDE.md §15) scores **0 and `eligible: false`**: §18 counts only explicitly configured methodologies. Validate with `python3 scripts/confluence.py` semantics if unsure and `engaged_count`. Compare against the mode **locked at step 3** — do not recompute the mode from this step's `engaged_count`, even if it differs from step 5's config-time count (e.g. a dimension that was configured on turned out live-unavailable): the mode stays whatever step 3 recorded, per the mode-lock rule (SOLO≥1, NORMAL≥2, ENHANCED≥3, STRICT≥3-explicitly-selected). If unmet: **verdict is NO TRADE**, skip to step 9.

7. **Contradiction Analysis.** Run this against **every** dimension whose data was AVAILABLE, not only the engaged ones (anti-cherry-picking rule). List bullish evidence, bearish evidence, and an explicit resolution for each contradiction found.

8. **Confluence Score.** Compute per `docs/architecture/SYSTEM-DESIGN.md` §6.2: `raw_pct = (sum of engaged-dimension points) / (engaged_count × 25) × 100`, subtract the Contradiction Penalty (percentage points), floor at 0 → `final_score`. Compare to the locked mode's threshold (SOLO 85, NORMAL 70, ENHANCED 80, STRICT 85) → `threshold_met`. `verdict = TRADE` only if `threshold_met` AND `dimension_count_met` AND no blocking HIGH event-risk-window contradiction; otherwise `WAIT` (close, salvageable with more confirmation) or `NO_TRADE` (structurally invalid).

9. **If verdict could be TRADE:** dispatch **risk-agent** with the candidate entry/stop/targets. If RiskAgent returns any hard-check FAIL, downgrade the verdict to NO_TRADE and say exactly which check failed — do not soften this.

10. **Trade Plan + Final Verdict.** Produce the full Decision Output per master spec §23 (Market State → HTF Context → Setup → Methodology Evidence → Independent Confluence → Confluence Score → Trade Decision → Invalidation & Management → Final Verdict).

11. **Journal.** Invoke journal-skill to write `trades/<id>.md` for any TRADE or WAIT verdict (NO_TRADE calls are logged too, but may be terser — still worth recording for later pattern review). Regenerate `trades/index.jsonl`.

12. **Never execute.** End with: "Analysis only. Run `/execute` for a manual execution ticket — no trade has been placed."
