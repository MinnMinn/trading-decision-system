# Institutional Trading Decision System — Architecture (v1)

Status: v1, adversarially reviewed (fork review, 2026-09-09) — one critical scoring-math bug found and fixed (§6.2), plus 6 smaller gaps closed (mode-lock, anti-cherry-picking, throttle reset, event calendar, risk config, rollup format). See inline "added after review" notes below for exactly what changed and why.
Owner spec: the master system prompt (institutional trading decision system, Wyckoff + ICT/TTrades + Footprint + Heatmap, capital preservation first).

This document is the single source of truth for how the system's Skills, Agents, Commands, and Hooks fit together, and how data flows from raw sources through validation, methodology analysis, confluence scoring, risk checks, to a trade decision and its journal record. Skills/Agents/Commands files reference this document rather than restating it (per single-source-of-truth discipline) — if this doc changes, those files should NOT need to change their own text, only their behavior.

---

## 1. Design principles carried over from the master spec

### 1.0 Two priority orders, two different questions (CLAUDE.md §1)

There are two orderings in this system and they are **not** competing versions of one list — they answer
different questions, and conflating them is how a latency argument ends up beating a research-integrity
argument. Neither is restated here beyond its one-line identity; `CLAUDE.md` §1 is the source for the second.

1. **Trading-outcome order** (the bullet immediately below, unchanged): what to protect when a *trade*
   decision trades one good against another. Capital first.
2. **Requirement-conflict order** (`CLAUDE.md` §1, 13 items, Safety → Convenience): what to protect when an
   *engineering* requirement trades one good against another — which is the order that settles "this check is
   too slow", "this abstraction is inconvenient", "can we cache that".

`CLAUDE.md` §1 closes with a hard list: **performance must never override** the six concerns below. That list
is the enforceable half of §1, so each item names where it is actually enforced today — and says so plainly
where it is not yet. Do not add a row claiming enforcement without a `path:line` that holds it.

| Performance may never override | Enforced today at | Status |
|---|---|---|
| research integrity | `scripts/live_rules.py:10` (`read_at` may not look past bar `i`), pinned by `scripts/tests/test_live_rules.py:101` (`class NoLookAhead`) | Partial — bar-index only; `available_time` does not exist on any record yet (CLAUDE.md §7/§8) |
| required decision dependencies | — | **NOT YET ENFORCED.** No Trading System declares REQUIRED_FOR_DECISION vs OPTIONAL_FOR_ANALYSIS (CLAUDE.md §35/§36/§62). This is the spec's own non-negotiable and the largest open gap in this document. |
| risk controls | `docs/architecture/risk-config.json` `max_risk_pct` → one validated reader `scripts/trading_env.py:69` (`MAX_RISK_PCT = _read_max_risk_pct()`), clamped at `scripts/strategy-runner.py:221` (`RISK_CEILING = trading_env.MAX_RISK_PCT`) | Enforced for the per-trade ceiling; account-level limits do not exist (CLAUDE.md §33) |
| event-risk controls | `scripts/event_risk.py`; `scripts/strategy-runner.py:405` (`def event_blackout(t=None, sym=None):`) delegates to it | **Fails CLOSED since 2026-09-18** — a missing, stale or unparseable calendar is UNAVAILABLE and applies the configured fail-safe (default BLOCK ENTRY), never "no news" (CLAUDE.md §32) |
| data-quality requirements | `docs/architecture/schemas/data-validation-status.schema.json:31` (`AVAILABLE`/`STALE`/`UNAVAILABLE`/`MOCK`), gate at §6.1 | Partial — `PARTIAL`/`INVALID`/`UNKNOWN` are unrepresentable (CLAUDE.md §20) |
| execution safety | `.claude/commands/execute.md:8` (one human confirmation, "REAL MONEY" in plain words), `execution` list of `docs/architecture/instruments.json` enforced by `scripts/instruments.py`, `scripts/strategy-runner.py:358` (`== "real"` refuses every tick) | Enforced |

`scripts/tests/test_spec_priority.py` pins this table against `CLAUDE.md` §1: if the spec's never-override
list changes, or a row is dropped from the table, the build fails. It deliberately does **not** check that a
row's claim is true — that is what the cited test at the end of each row is for.

- Capital preservation > decision quality > consistency > expectancy > continuous improvement, in that order, always.
- Confluence Score (0–100) is a **decision-quality** measure, not a win-probability estimate, until statistically calibrated.
- Missing data is never confirmation. A methodology requirement that cannot be evidenced is a failed requirement, not a neutral one.
- Analysis and execution are separately permissioned. Two execution paths exist: `/execute` (manual, one explicit human confirmation per trade, SPOT LONG only, on the `execution` list of `docs/architecture/instruments.json`) and the rules-only pilot started by `/automation` (unattended, §9.x). Both trade the **active environment** — `demo` (Binance TESTNET) or `real` (Binance MAINNET, real money) — selected by `docs/architecture/automation-config.json` → `execution.environment` and the credentials in `config/env.<environment>` (user decision 2026-09-10: the environment is the human's switch; nothing in the code refuses mainnet on policy grounds any more). An environment file with placeholder secrets refuses to execute (correctness, exit 2).
- No instrument outside the allowlist below without explicit user approval. ("No Forex, ever" stood here until 2026-09-17, when the user lifted it. It was always redundant with the allowlist -- see §1's allowlist paragraph -- and the allowlist is the rule that is actually enforced.)
- **Instrument allowlist — one source, two lists.** The symbols live in **`docs/architecture/instruments.json`** and nowhere else; `scripts/instruments.py` (Python) and `scripts/instruments.sh` (bash) are the only readers, the JSON-Schema enums are generated by `scripts/sync-instruments.py --write`, and `scripts/tests/test_instruments_sync.py` fails the build if any copy drifts. **Do not restate the symbols in this document or any other** — cite the file. The file carries two lists per market and the distinction is the safety property: **`analysis`** = scannable and analysable (scanner, `/analyze`, `/bias`, `/entry`); **`execution`** = orderable (the pilot, `/execute`, the Binance connectors), always a strict subset that `instruments.py` enforces on load. A symbol added to `analysis` alone is **watch-only and can never reach a venue**. Widening `execution` is a separate decision needing its own explicit authorization — granted for all nine crypto symbols on 2026-09-12, so `execution.crypto` now equals `analysis.crypto`. **The six added symbols carry no measured edge:** the `pilot-top20.json` setups were backtested on BTCUSDT/ETHUSDT/SOLUSDT only (see each setup's `backtest.source`), so live results on ASTER/VIRTUAL/SUI/TAO/RENDER/ONDO are an experiment, not a validated strategy. The pilot's live loop trades `enabled_symbols()` (the `execution` list ∩ the automation config), NOT each setup's `symbols` field — `strategy-runner.py` `replay()` uses the same universe so parity is checked on what actually trades. Changes are appended to the file's own `history` array; the 2026-09-12 entry (six altcoins, watch-only, on explicit user approval) supersedes the refusal recorded in `automation-config.json` history at 2026-09-12T07:35:27Z. Not yet covered by the allowlist widening: the published chart artifacts and headless local reads, still built for the core three (`scripts/build-artifact.py` `CRYPTO`, `integrations/headless/*.md`).

## 2. Data flow (maps onto the master spec's 12-step pipeline)

```
Data Validation ──► Event Risk ──► Market Regime ──► HTF Context ──► Setup Detection
      │                                                                    │
      ▼                                                                    ▼
DataSource Layer                                              Methodology Analysis
(exchange market data / CoinGlass,                            (WyckoffSkill, ICTSkill,
 real or mock — §3)                                            FootprintSkill, HeatmapSkill)
                                                                            │
                                                                            ▼
                                                          Independent-Confluence Check
                                                          (StructureAgent + FlowAgent +
                                                           LiquidityAgent inputs merged
                                                           by DecisionAgent — §6)
                                                                            │
                                                                            ▼
                                                          Contradiction Analysis + Score
                                                          (DecisionAgent — §6.2)
                                                                            │
                                                                            ▼
                                                          Risk Validation (RiskAgent — §7)
                                                                            │
                                                                            ▼
                                                          Trade Plan + Verdict (DecisionAgent)
                                                                            │
                                                                            ▼
                                                          Journal write (JournalSkill — §8)
                                                                            │
                                                                            ▼
                                                          Human Decision / /execute (§9)
```

Every box above is implemented by a named Skill/Agent/Command in §§4–9. Nothing in this pipeline is allowed to skip the Data-Validation gate — every command that touches market data starts there.

## 3. Data Source Layer (real + mock)

Full contract: `docs/architecture/data-sources.md`. Summary:

- **Crypto market data — LIVE.** `scripts/fetch-binance-klines.sh` pulls real Binance public REST data (no API key needed), verified against every crypto symbol on the `analysis` list of `docs/architecture/instruments.json` (1m/15m/1H/4H/1D fetched 2026-09-12). Written to `data/live/market-data/`. Note the timeframe argument is case-sensitive: `1H`/`4H`/`1D`, but `1m`/`5m`/`15m`/`30m`.
- **Commodities market data — bridge built, untested against a real terminal.** An MT5 file-bridge (`integrations/mt5/ExportOHLCV.mq5` writing to `data/live/mt5-bridge/`) replaces the earlier "third-party provider TBD" plan — see `docs/architecture/mt5-bridge.md`. Caps XAUUSD/XAGUSD/USOIL/UKOIL analysis at 2 of 4 dimensions (Wyckoff + ICT only — Footprint/Heatmap need CoinGlass, which doesn't cover commodities), so NORMAL mode is the ceiling for these instruments until an order-flow source for MT5 markets exists. The bridge feeds the three CFD scanner styles — `cfd-scalping` (15m), `cfd-day` (1h), `cfd-swing` (4h), the same three horizons as crypto (`scripts/automation.py:142` (`HORIZON_TF = {"scalping": "15m"`); bar counts from `SCAN_WINDOW`, `automation.py:154` (`SCAN_WINDOW = {`)) — and no 1m style, because the EA exports 1W/1D/4H/1H/15m/5m only for one charted symbol at a time (§12 item 6). TradingView MCP was considered and dropped: TradingView has no official public data API, and the community MCP servers for it rely on browser automation or unofficial scraping. See `docs/architecture/data-sources.md` for the full rationale.
- **CoinGlass** — footprint history, liquidation heatmap, orderbook heatmap, delta/CVD, open interest, funding. No API key configured yet — still MOCK.
- `mock/market-data/` and `mock/coinglass/` remain available for deliberate rehearsal runs even after real connectors exist — same field shape, so Skills never change regardless of which mode is active.
- **Every** Data Validation Status report (§4.1 in WyckoffSkill/FootprintSkill/HeatmapSkill, and the shared status block emitted by every command) MUST show a 4th state, **MOCK**, distinct from AVAILABLE/UNAVAILABLE/STALE, whenever fixture data is in use — this is a hard rule, not a style choice, so a mock-mode run can never be mistaken for a live-confirmed one. See `docs/architecture/data-sources.md` §"Mock-mode integrity rule".

## 4. Skills (7)

| Skill | Owns | Reads |
|---|---|---|
| **WyckoffSkill** | Phase A–E event walk, the đối nhãn mislabelling tests, CO plan, Spring/Upthrust typing in two separate fields, Trading-Range/fractality reads, Effort-vs-Result, tape reading (spread×volume), SOT, structural absorption, Urgent Demand, **and Volume Profile (VAH/VAL/LVN/VPOC) including its abandon-rule veto** | **`knowledge/wyckoff/advance.md` (primary)**, `knowledge/integrated/method.md` §2 (procedure), `knowledge/wyckoff/modern-tools.md` §2.6–2.7 (Spring/Upthrust types), `knowledge/footprint/wyckoff-logic.md`–`knowledge/footprint/chart-delta.md` (second author's Wyckoff content) |
| **ICTSkill** | Market structure (MSS/CISD — **not** BOS/CHOCH, which are unsourced), OB/FVG/Breaker/Mitigation, liquidity (IRL/ERL), OTE, premium/discount, session timing per `session-model.md`, SMT, PO3/AMD, TTrades models. **Does not own Volume Profile** — it consumes WyckoffSkill's verdict | `knowledge/ict/core-a.md`–`knowledge/ict/models.md`, `knowledge/integrated/wyckoff-ict-mapping.md` (de-duplication), `knowledge/integrated/method.md` §4 |
| **FootprintSkill** | Order-flow read: POC, R/H/R/L, Imbalance/Stacked Imbalance, Absorption/Exhaustion/Development, Delta/Cumulative-Delta divergence, Tape Reading with Delta | `knowledge/wyckoff/modern-tools.md` §3–§5 (primary), `knowledge/footprint/wyckoff-logic.md`–`knowledge/footprint/chart-delta.md`, `knowledge/integrated/method.md` §3 (event→signature bridge) |
| **HeatmapSkill** | Liquidation clusters, orderbook liquidity, liquidity sweeps/targets — **no dedicated source doc exists**; this skill's rules come from the master spec only (flagged gap, see `docs/architecture/data-sources.md`) | CoinGlass (real/mock) |
| **RiskSkill** | Position sizing, R:R calc, max-risk enforcement, consecutive-loss throttle | `docs/architecture/schemas/risk-calculation.schema.json` |
| **JournalSkill** | Writes/updates the per-trade record; generates Edge Log and Mistake-DB rollup views | `trades/*.md`, `docs/architecture/schemas/trade-file.schema.json` |
| **LearningSkill** | Post-trade review synthesis, pattern detection across `trades/*.md`, drafts improvement proposals per the Observe→Measure→Pattern→Propose→Validate→Approve→Deploy loop | `trades/*.md`, this doc §11 |

Each Skill is a thin *procedure* wrapper: it states what to check, in what order, citing the exact `knowledge/` file/section for the underlying theory, and never restates that theory inline.

## 5. Agents (6)

Agents are the reasoning roles a Skill's procedure gets executed *as*. **Concrete implementation decision:** StructureAgent, FlowAgent, LiquidityAgent, RiskAgent, and LearningAgent are real Claude-Code subagents (`.claude/agents/*.md`, dispatchable via the Agent tool, read-only tool access except JournalSkill/LearningSkill's own write paths) — this gives each a genuinely independent, auditable analysis pass and lets Structure/Flow/Liquidity run in parallel when a Command chooses to. **DecisionAgent is deliberately NOT a dispatched subagent** — it is the orchestration logic embedded directly in the `/analyze` (and `/entry`) command file, because reconciling four dimensions' worth of citations into one coherent, contradiction-checked score is a synthesis task that benefits from full context in one place rather than a second layer of agent-to-agent summarization risk. This is a considered simplification, not an oversight — it avoids over-engineering a solo-trader tool into a distributed system while still keeping the four analytical roles modular and separately callable.

| Agent | Role | Primary Skill(s) | Answers |
|---|---|---|---|
| **StructureAgent** | Wyckoff + ICT structure/location read | WyckoffSkill, ICTSkill | What is the market doing, and where/when could a setup occur? |
| **FlowAgent** | Order-flow confirmation | FootprintSkill | What is actually happening inside the move? |
| **LiquidityAgent** | Liquidity/positioning read | HeatmapSkill | Where is liquidity, and what is price attracted to/against? |
| **RiskAgent** | Position sizing, invalidation, hard-rule enforcement | RiskSkill | Is this trade sized and stopped safely? |
| **DecisionAgent** | Merges StructureAgent + FlowAgent + LiquidityAgent, runs the Independent-Confluence Check, Contradiction Analysis, Confluence Score, and issues the final verdict | (none directly — orchestrates) | Trade / Wait / No Trade, and why |
| **LearningAgent** | Runs LearningSkill's review/pattern/proposal loop; **cannot** modify safety-critical rules (§11) | LearningSkill | What should the system learn, and is it enough evidence to act on? |

## 6. DecisionAgent — confluence engine (the core scoring logic)

### 6.1 Independent-Confluence Check
Each of Wyckoff/ICT/Footprint/Heatmap can contribute **at most once** to the "how many methodologies are satisfied" count, regardless of how many individual signals it produced (per the master spec's "no duplicate evidence as independent confluence" hard rule — e.g. a liquidity sweep + a liquidation cluster + orderbook removal are one Heatmap-dimension observation, not three). A dimension counts as "satisfied" only if:
1. Its required input data is `AVAILABLE` (not `MOCK`, not `STALE`, not `UNAVAILABLE`) for a **live** trade decision — `/analyze` in mock mode may still run for rehearsal/testing, but its own output must say "SIMULATED — not eligible to satisfy a live methodology-mode requirement," and
2. It produced a concrete, cited observation (not "no contradiction found").

**Wyckoff/ICT independence is not automatic (added 2026-09-10).** `knowledge/ict/core-a.md`–`knowledge/ict/models.md` contain **no volume of any kind**, so volume is the only genuinely orthogonal axis between the Wyckoff and ICT dimensions — everything else the two traditions appear to confirm in each other is price geometry read twice (`knowledge/integrated/wyckoff-ict-mapping.md` §3, `knowledge/integrated/method.md` §4.1). Before both dimensions score the same location or the same structural break, StructureAgent MUST print the Wyckoff event-derived price and the ICT swing-derived price and state whether they differ. If they are the same level, the phenomenon scores in **one** dimension only, per the assignment rules in `knowledge/integrated/method.md` §4.3 (Wyckoff owns the excursion and its volume typing; ICT owns the structural break and the location sub-levels). On tick-volume feeds (the MT5 bridge — XAUUSD/XAGUSD/USOIL/UKOIL) the two dimensions are close to non-independent and Wyckoff credit must be reduced rather than both scored at face value.

Methodology Mode minimums (unchanged from the master spec): NORMAL ≥2, ENHANCED ≥3, STRICT ≥3 explicitly-selected + zero unresolved high-impact contradictions. If the count is unmet, DecisionAgent must return **NO TRADE**, full stop — it may not add a methodology just to reach the count (hard rule).

**SOLO mode (added 2026-09-12, user's explicit decision — changes this master-spec-inherited rule).** `wyckoff` and `ict` are the two presets in `docs/architecture/methods.json` that engage exactly one Confluence dimension; under the minimums above they could never produce a live TRADE verdict, no matter how strong the read, which made them permanently research-only. The user chose to make them usable for real entries via a fifth mode, **SOLO: minimum 1, threshold 85** (§6.2 records the reachability check and the mode/threshold table). SOLO is **not** a generally-selectable mode the way NORMAL/ENHANCED/STRICT are — see the mode-lock rule in §6.2 for the exact restriction that keeps this from reopening the "downgrade after the fact" hole the mode-lock exists to close.

### 6.2 Confluence Score — rubric

**Dimensions, runner methods and presets — one source (2026-09-12).** The Confluence dimensions (with each one's `max_points`, market list, agent and skill), the runner-method table (`requires[]` / `runnable` / `scan` / `entry`) and the named method presets live in **`docs/architecture/methods.json`** and nowhere else. `scripts/methods.py` is the only reader, `scripts/sync-methods.py --write` regenerates the derived JSON-Schema spots — `markets.<m>.dimensions` in `schemas/automation-config.schema.json` is now **generated** from each dimension's `markets[]` list instead of being hand-written — and `scripts/tests/test_methods_sync.py` fails the build if any copy drifts. **Nothing else in this repo may hard-code a dimension name, a runner method or a preset** — cite the file, exactly as §1 does for the instrument allowlist. Design and rationale: `docs/specs/2026-09-12-method-switch-design.md`; the panel's threat model and rules: `docs/security/2026-09-12-method-panel.md`.

**Corrected after adversarial review — the first draft had a critical bug: capping every dimension at 25/100 flat made the STRICT-mode 85 threshold mathematically unreachable with only 3 dimensions engaged (3×25=75 max), silently forcing all 4 dimensions every time and contradicting the master spec's own "3 or more" wording. Fixed by scoring against the *engaged* maximum, not the flat 0–100 scale:**

1. Each dimension a Skill actually analyzes (regardless of mode) gets 0–25 raw points from its own evidence checklist below, but is only **eligible/"engaged"** if BOTH (a) the active preset engages it (§18 — being *analysed* under §15's `available` scope is not enough; see §30) and (b) its data source is `AVAILABLE` (not `MOCK`/`STALE`/`UNAVAILABLE`) per §6.1. Unavailable or not-analyzed dimensions score 0 and do not count toward `engaged_count`.
2. `raw_pct = (sum of points across engaged dimensions / sum of those same dimensions' max_points) × 100`. The per-dimension maximum is `dimensions.<name>.max_points` in `docs/architecture/methods.json` — **25 for all four dimensions today**, so the denominator currently evaluates to `engaged_count × 25` and every number in this section is unchanged from the previous wording. Stating it as a sum rather than a count × 25 is what makes the rubric independent of the dimension count: **adding a fifth dimension (or one with a different `max_points`) is a registry entry, not an edit to this formula.** Worked example, unchanged: 3 engaged dimensions scoring 22/25 each → sum of points = 66, sum of `max_points` = 25 + 25 + 25 = 75, so `raw_pct = 66/75 × 100 =` **88**, correctly clearing STRICT's 85 threshold. If no dimension is engaged the denominator is 0 and `raw_pct = 0` by definition (not a division).
3. Subtract the **Contradiction Penalty** (percentage points, not raw points) from `raw_pct`: major opposing HTF structure (−15), major opposing liquidity/liquidation cluster (−10), event-risk within the pre-event blackout window (−20, and independently forces NO TRADE regardless of score — see §6.3). Multiple contradictions stack; floor at 0.
4. `final_score = max(0, raw_pct + penalty_total)`, where `penalty_total` is the (negative) sum of contradiction penalties in percentage points — e.g. `raw_pct = 82`, one high-impact contradiction `penalty_total = −20` → `final_score = 62`. (Sign convention matches `schemas/confluence-score.schema.json`: `penalty_total ≤ 0`.) Compare against the flat mode threshold (70/80/85) — this comparison is now meaningful at any engaged-dimension count.

Per-dimension partial credit (illustrative point allocation inside each dimension's `max_points`, 25 for all four today; a Skill's own procedure is the authority on what evidence maps to which bucket):
- **Wyckoff (25):** phase clarity **after the đối nhãn mislabelling tests** (`knowledge/wyckoff/advance.md` §2.11) (0–8), event identification and typing quality in both vocabularies (0–10), Effort-vs-Result / tape-reading / SOT evidence (0–7). The volume component is **reduced on tick-volume feeds** (MT5 bridge) — see the independence rule below.
- **ICT (25):** HTF structural falsification check (0–8), structure/location quality — OB/FVG/liquidity/OTE (0–10), timing per `docs/architecture/session-model.md` weight classes (0–7). Score **after** applying the Wyckoff/ICT de-duplication rules (`knowledge/integrated/method.md` §4.3).
- **Footprint (25):** absorption/exhaustion/development read (0–10), Delta/Cumulative-Delta divergence strength (0–8), Tape-Reading case alignment (0–7).
- **Heatmap (25):** liquidity-sweep/target alignment (0–10), liquidation-cluster interaction (0–8), orderbook positioning (0–7).

**Numeric thresholds live in `docs/architecture/analysis-params.json`**, split into a `sourced` block (page-cited values from the books) and a `project_defined` block (values no source gives — low/high volume, narrow/wide spread, commitment bars, the same-level tolerance for the de-duplication check, the tick-volume credit multiplier). Outputs must label `project_defined` values as project parameters. They are the tuning surface for `/improve`.

**Score threshold AND dimension-count minimum are both required, independently** — `dimension_count_met` (engaged_count ≥ mode minimum) is a separate boolean gate from `threshold_met` (final_score ≥ mode threshold). `verdict = TRADE` requires **both** true, plus no blocking event-risk contradiction. This still closes the original loophole (one dimension alone can't "buy" a pass under NORMAL/ENHANCED/STRICT, since a lone engaged dimension can never meet a ≥2 count minimum there) without breaking STRICT mode's math. SOLO mode (below) is the one deliberate, registry-declared exception to the ≥2 floor, compensated by a higher score threshold rather than a lowered one.

**SOLO mode — minimum, threshold and the reachability check (added 2026-09-12, user's explicit decision).** `docs/architecture/methods.json` now carries a `modes` table (`minimum`/`threshold` per mode) and a `mode` field on every preset: `NORMAL` (min 2, threshold 70), `ENHANCED` (min 3, threshold 80), `STRICT` (min 3, threshold 85) are **unchanged** from the master spec; **`SOLO` (min 1, threshold 85) is new** and applies only to the `wyckoff` and `ict` presets — the only two that themselves name exactly one dimension. `scripts/methods.py` reads this table instead of a hand-kept constant.

*Reachability, checked before shipping this number (this exact bug — an unreachable threshold — bit STRICT's first draft, see the correction note above):* with one dimension engaged, `raw_pct = (points / dimensions.<name>.max_points) × 100 = (points / 25) × 100` (§6.2 item 2). SOLO's 85 therefore needs **21.25 of 25 points from that one dimension's own rubric** — attainable at, e.g., 22/25 (88%): for Wyckoff, 7/8 phase clarity + 9/10 event identification/typing + 6/7 EvR-tape-SOT; for ICT, an equivalent near-flawless-but-not-literally-perfect split across its 8/10/7 buckets (item "Per-dimension partial credit" above). This is a genuinely demanding bar — a single methodology has no cross-confirming dimension to lean on, so it must clear the same score STRICT needs from three — but it is mathematically reachable at the registry's own point scale (max is 25/25 = 100%), unlike the original STRICT bug where the *ceiling itself* (75/100 under the old flat-scale formula) sat below the threshold. 85 was kept as designed; it is demanding, not a fake option.

**SOLO applies to the preset, never to the runtime engaged count (this is the whole safety argument for the mode).** The mode-lock rule below already forbids downgrading a run's mode after the fact to make a weak result pass. SOLO is a second surface for the exact same failure mode: if a run's mode were *derived from how many dimensions turned out to be engaged*, a user who deliberately selected a two-dimension preset (e.g. `wyckoff+footprint`, mode NORMAL) would silently get SOLO's easier minimum (1) whenever a dimension became unavailable at runtime (CoinGlass down, a stale feed, etc.) — reaching TRADE on a single dimension despite never having chosen SOLO. This is forbidden: **a preset's mode is fixed by its own `mode` field in the registry, decided at preset-selection time, before any analysis — never recomputed from `engaged_count`.** A multi-dimension preset that degrades to one engaged dimension at runtime keeps its original mode (e.g. NORMAL) and returns NO TRADE on count, exactly as it did before SOLO existed. `scripts/methods.py`'s `dispatch_plan()` enforces this: `mode` comes from `profile_of()` on the **configured** dimension flags only; a live-unavailable dimension (passed separately) can only lower `engaged_count`, never change `preset`/`mode` (`scripts/tests/test_methods.py::DispatchPlan::test_trap_a_degraded_multi_dimension_preset_never_reports_solo`).

**Anti-cherry-picking rule (added after review):** a trader/agent may not simply stop analyzing once the mode minimum is reached while leaving other *available* data unchecked. Contradiction Analysis (§7 of the master spec) MUST run against **every dimension whose data source is `AVAILABLE`**, not just the ones counted toward the minimum — an available-but-unengaged dimension's contradictions still apply their full penalty. Only a dimension that is genuinely `UNAVAILABLE`/`STALE`/`MOCK` is exempt from this contradiction sweep, because there is no evidence to check.

**Mode-lock (added after review, closes a missing master-spec hard rule):** DecisionAgent must select and record `methodology_mode` as the very first scoring step, before any dimension is analyzed, and it is immutable for the rest of that analysis run — never downgraded after the fact to make a weak result pass (master spec §3/§9). **With SOLO added (2026-09-12), this now explicitly includes: the mode is taken from the selected preset's own `mode` field (`docs/architecture/methods.json`, via `scripts/methods.py`'s `dispatch_plan()`), never inferred from `engaged_count` once live data validation runs** — see "SOLO applies to the preset, never to the runtime engaged count" above.

### 6.3 Regime and Event-Risk gates (run before scoring, not after)
- Market Regime = TRENDING / RANGING / TRANSITIONAL / UNCLEAR, per StructureAgent's read. If UNCLEAR and the candidate setup is regime-dependent (e.g. a range-Spring thesis inside what might actually be a strong trend), DecisionAgent must reduce the Wyckoff/ICT dimension credit or return NO TRADE — never silently assume RANGING.
- Volume-Profile abandon rule = FIRED / NOT FIRED, per WyckoffSkill (`knowledge/wyckoff/modern-tools.md` §5 Step 4, WMT p243–p249). If price crossed cleanly through VAH/VAL into the LVN **without a reversal reaction**, the Spring/Upthrust thesis is dead: return NO TRADE. This is a veto evaluated before scoring, not a point deduction — it is the strongest thesis-invalidation statement in either source tradition, and Volume Profile belongs to the Wyckoff dimension by user decision 2026-09-10.
- Event Risk = **HIGH / MEDIUM / LOW / UNKNOWN** (CLAUDE.md §25's own vocabulary; this line said MODERATE until 2026-09-18, which was a third word for a level the spec names), computed by `scripts/event_risk.py` from **`docs/architecture/event-calendar.json`** — see §40 below for the whole subsystem. The calendar is hand-maintained with no automatic feed in v1; the user, or LearningSkill via `/improve`, never silently, updates it. A calendar that is absent, unparseable, or past its own `covers_through` is UNAVAILABLE and applies the configured fail-safe (default BLOCK ENTRY) — an unmaintained calendar is a data-quality gap, not a clean bill of health. HIGH inside a restricted window forces the −20 penalty above regardless of everything else, and should usually still resolve to NO TRADE / WAIT even at a high raw score, per the master spec's explicit "never treat technically perfect pre-event structure as automatically safe."

## 7. RiskAgent / RiskSkill — position sizing and hard limits

Inputs: account equity and default risk % are read from **`docs/architecture/risk-config.json`** (a small user-edited config, so they don't need to be re-supplied on every call), overridable per-command with an explicit parameter. The hard ceiling is `max_risk_pct` in that same file (1% today) — THE ceiling for every order path, manual and automated alike, read through `trading_env.MAX_RISK_PCT`; never overridable above it without an explicit typed override that RiskSkill logs as a flagged exception in the resulting trade file. Outputs: position size, dollar risk, R:R at each target, and a PASS/FAIL against every §15 "Necessary Condition" in the master spec (clear invalidation, defined stop, acceptable R:R, etc.).

**Consecutive-loss throttle:** RiskSkill reads the last closed, **non-rehearsal** trades from `trades/*.md` (§8) — rehearsal-mode trades never count, per their schema flag — counting consecutive `result: LOSS` entries back from the most recent closed trade. After 2 consecutive losses, it must recommend halving size or pausing, per the master spec §20. **Reset condition (added after review — the first draft left this undefined):** the throttle deactivates the moment either (a) one subsequent trade closes as a `WIN`, restoring normal risk %, or (b) the user explicitly overrides via `/risk` with a logged reason. Absent either, the throttle stays active indefinitely — it does not silently expire after a time window.

Hard, non-negotiable checks RiskAgent performs on every `/analyze`, `/entry`, and `/execute` call (mirrors master-spec §25 Hard Safety Rules 2–5):
- Risk % ≤ `risk-config.json` `max_risk_pct` — reject and recompute if violated; refuse outright if that value cannot be read.
- A Stop Loss and an invalidation level both exist and are distinct concepts (price vs. thesis vs. data invalidation, §21) before any BUY/SELL verdict is allowed to stand.
- No "average down," no "widen stop after entry," no "remove stop" — these are refused outright, not merely flagged, if requested via `/entry` or `/execute` on an already-open position.

## 8. JournalSkill — storage design

No database exists in v1. One Markdown file per trade under `trades/<YYYY-MM-DD>-<PAIR>-<seq>.md`, YAML frontmatter matching `docs/architecture/schemas/trade-file.schema.json`, body = the full Decision Output (master spec §23) at plan time, appended with the Post-Trade Review (§26) fields at close time. This single file **is** the Journal entry, the Edge-Log entry, and — if flagged — a Mistake-DB entry.

**Rollup mechanism (made concrete after review — "queryable" was hand-wavy in the first draft):** JournalSkill regenerates **`trades/index.jsonl`** on every `/journal` or `/status` call — one JSON line per trade file, containing exactly its YAML frontmatter, rebuilt by scanning `trades/*.md` fresh each time (never hand-edited, always derived). `docs/edge-log/EDGE-LOG.md` and `docs/mistakes/MISTAKE-DB.md` are then simple filtered/formatted views over `trades/index.jsonl` (e.g. Edge Log = every closed, non-rehearsal trade sorted by date; Mistake DB = every trade with `is_mistake: true`, grouped by `root_cause`) — cheap to regenerate, never a second hand-maintained copy of the data. This is a deliberate simplification from the master spec's three-named-artifact language — same information, one source of truth, per this project's own single-source-of-truth rule. `trades/README.md` documents the format.

### 8.1 Journal tooling (2026-09-10)

`scripts/journal.py` operates the store: `sync-pilot` ingests the pilot runner's entry/exit records into `trades/*.md`
(idempotent on the exchange entry order id; computed fields — R, P&L, hold time, exit type, session — filled by code),
`review <id> --set k=v` records the human/Claude review fields (root_cause, is_mistake, lessons, review_notes,
what_to_change, followed_plan, confidence, emotional_state, tags, screenshots), `index`/`views` regenerate
`trades/index.jsonl`, `docs/edge-log/EDGE-LOG.md` and `docs/mistakes/MISTAKE-DB.md`, `stats` computes win rate,
average/expectancy R, profit factor, max drawdown in R, losing streaks and breakdowns by setup/instrument/session/market,
and `render` writes the Vietnamese review page published as the "Nhật ký giao dịch" artifact. The schema gained the
review fields listed above plus `market`, `source`, `timeframe`, `leverage`, `planned_rr`, `pnl_usd`, `fees_usd`,
`slippage_bps`, `hold_minutes`, `exit_type`, `thesis`, `plan_vs_actual`, `exchange_refs`; `confluence_score` may be
null for rules-only pilot trades.

## 9. Commands (12)

| Command | Pipeline steps it runs | Can it move toward execution? |
|---|---|---|
| `/analyze` | Full 1–11 (Data Validation → Trade Plan) | No — analysis only |
| `/bias` | 1–4 (through HTF Context) | No |
| `/entry` | 5–10 for an already-identified setup (fine timing/entry-signal check) | No |
| `/exit` | Invalidation + management check on an OPEN trade from `trades/` | No |
| `/risk` | RiskSkill sizing calculator standalone (given entry/stop/equity) | No |
| `/journal` | JournalSkill write/update | No |
| `/invalidate` | Re-checks price/thesis/data invalidation on one open trade | No |
| `/status` | Data Validation snapshot + open-position summary + rollup views | No |
| `/review` | Post-Trade Review (§26) on a closed trade | No |
| `/improve` | LearningAgent's Observe→Propose loop (§29–31), always outputs KEEP/TEST/ADOPT/REJECT, never silently changes rules | No |
| `/automation` | Configuration, plus the one process action below. Turns the three real background layers on/off (layer 1 scanner `scripts/scan-loop.sh`, layer 2 local read `scripts/local-eval-brief.py`, the pilot `scripts/strategy-runner.py` — one engine since 2026-09-13) and scopes them **per market** (`crypto` / `cfd`) by Confluence dimension (§6.2), **method preset**, timeframe and instrument. **Three subcommands added 2026-09-12 with the method switch** (`docs/specs/2026-09-12-method-switch-design.md`): **`method <preset> [--market crypto|cfd]`** applies one of the named presets in `docs/architecture/methods.json` as a set of dimension flags — a preset is only a *name* for that set, nothing extra is stored (`scripts/automation.py:1122-1123` (`def cmd_method(a):`)); it refuses (exit 2) a preset whose dimensions the target market has no source for, and with no `--market` it applies only to the markets that can hold it and says which it skipped. **All six presets and the control panel are unchanged** — `wyckoff`, `ict`, `wyckoff+ict`, `wyckoff+footprint`, `wyckoff+ict+footprint`, `full` (user decision 2026-09-13: the method switch stays exactly as it is). **`instrument set <SYM,SYM,...> --market <crypto|cfd>`** replaces that market's whole instrument list in **one write and one history row** instead of N rows, all-or-nothing on any invalid symbol, re-validating independently of the caller (`automation.py:1226-1239` (`def cmd_instrument_set(a):`)). **`allows master`** is a shell gate that exits 0 only when the config exists **and** `enabled` is true — it deliberately fails **closed** on a missing or corrupt file, unlike `allows scanner|local_read|pilot`, which treat "unconfigured" as permitted (`automation.py:1269-1248` (`def cmd_allows(a):`)). Related behaviour change: **`demo` / `real` no longer reset the dimension flags** — the chosen method preset survives an environment switch (`automation.py:14-17` (`demo / real ->`) docstring; spec §4.1). `(market, timeframe)` resolves to the chart-style vocabulary through ONE authored table — three horizons, one timeframe each, both markets: `automation.HORIZON_TF` at `automation.py:142` (`HORIZON_TF = {"scalping": "15m"`), from which the flat style names are *derived* at `automation.py:149` (`STYLE = {(m, HORIZON_TF[h])`) — crypto keeps the bare horizon word, cfd takes a `cfd-` prefix. Read that table; do not restate the names here. The scanned timeframe set is `15m`/`1h`/`4h` for every market (`automation.py:115` (`MARKET_TIMEFRAMES = {m: list(_SCANNED_TF)`)); `1D` and `1W` are context rungs, fetched and never scanned, so `timeframe 1D on` is a usage error (no cfd 1m — §12 item 6; no cfd footprint/heatmap keys at all — §12 item 3). Writes `docs/architecture/automation-config.json` (`schema_version: 2`, schema `schemas/automation-config.schema.json`) through its single writer `scripts/automation.py` (§13 rule 3), with a who/when/what audit trail including refusals. `status` is the default and is safe to run at any time; `demo` is a one-command preset. | **It writes flags, and it may start/stop the TESTNET pilot when the human asks in-session.** `/automation demo` and `/automation pilot start` are that ask (§9.x); Claude never *schedules* the pilot and never loads the launchd plist. `pilot start` refuses (exit 2) on master-off, `layers.pilot` off, `markets.crypto` off, an **incomplete `config/env.<environment>` file**, a present `STOP` file, or any pilot loop already running — including an unrecorded one the user started by hand (`automation.py:1292-1306` (`def pilot_start(a, cfg=None, embedded=False):`)). `off` / `pilot stop` drop the kill switch and never remove it again — one venue since 2026-09-13, so one path, `data/live/pilot-futures/STOP` (`automation.py:244` (`PILOT_STOP = [stop_path(m) for m in PILOT_MARKETS]`)). **There is no environment policy gate here** (corrected 2026-09-12; the old text claimed `execution.account != demo_testnet` and "mainnet execution stays prohibited", both of which describe a field and a rule that no longer exist). `execution.environment` is the human's switch, and per §1 nothing in the code refuses mainnet on policy grounds; the only environment check `pilot start` makes is that the env file is filled in, which is a correctness check. What *does* keep the unattended pilot off mainnet today is narrower and lives elsewhere: `strategy-runner.py:358` (`== "real"`) refuses every tick when `execution.environment == "real"` (user decision 2026-09-11, demo/testnet pilot first), so the loop may start in `real` but will not trade. Any off-allowlist instrument is refused outright (§1) -- including a currency pair, which since 2026-09-17 is judged on that ground alone. |
**Method control panel (added 2026-09-12).** A published Artifact page at
`https://claude.ai/code/artifact/819225e6-f2cc-4299-a4af-c606efd3044d` lets the human tap a method preset and the
instrument list per market. Generated by `scripts/method-panel.py` (same rule as every other page: numbers from
code, §15); the URL lives in the front matter of `integrations/crons/method-switch.md`, which is the applier —
a session cron every 5 minutes that reads the page's `db`, validates, and calls `scripts/automation.py method` /
`instrument set` with `--who artifact-panel`. It is gated on the master switch alone (`layer: none`) and proceeds
only on `allows master` exit 0. Design: `docs/specs/2026-09-12-method-switch-design.md` §4.4-§4.5; threat model
and the 38 binding rules: `docs/security/2026-09-12-method-panel.md`.

**Do not share that artifact with anyone.** Declaring the `db` capability makes an artifact organization-internal,
so the audience is every signed-in member of the org, and the `user` capability is not available to this account —
the page structurally cannot record who tapped. The write rule `{"path": "", "read": "owner", "write": "owner"}`
is the only control, and the page says so on its face.

| `/execute` | Separately-permissioned; see below | **Stage 1 — built and verified.** (a) requires one explicit human confirmation per trade, distinct from a prior `/analyze` TRADE verdict, (b) re-runs RiskAgent's hard checks one last time, (c) on confirmation, submits a real market-buy + OCO exit bracket through `scripts/binance-testnet-order.sh` — a **stale name**: the script takes `BASE_URL` from `BINANCE_SPOT_BASE_URL` (`binance-testnet-order.sh:40` (`BASE_URL="$BINANCE_SPOT_BASE_URL"`)), which `scripts/trading-env.sh` loads from `config/env.<environment>`, so it hits `testnet.binance.vision` under `demo` and `api.binance.com` under `real`. **Corrected 2026-09-12: this command is NOT testnet-only.** Per §1 it places the order on the active environment, and under `real` that is Binance MAINNET with real money — `.claude/commands/execute.md:8` already stated this correctly and required the confirmation prompt to say "REAL MONEY" in plain words every time. Remaining scope limits, which are real: LONG-only (no spot shorting), the `execution` list of `docs/architecture/instruments.json` only (no commodities connector exists), one explicit human confirmation per trade, and never unattended — a scheduled/cloud context may flag a candidate but the submission step always happens in an interactive turn. MT5 execution and removing the per-trade confirmation (Stage 2) remain separate, larger decisions requiring their own explicit authorization. |

### 9.y The pilot engine (2026-09-11, user decision; TESTNET only — collapsed to one engine 2026-09-13)

**One engine, one venue, no profile switch (user decision 2026-09-13).** `scripts/strategy-runner.py` is the pilot. The `execution` profile key that used to choose between two engines, and the second engine itself, are both deleted; `layers.pilot` alone expresses "run nothing", which is the only thing that key could still have said (`strategy-runner.py:356` (`there is one engine now`)). The one venue is futures — `PILOT_MARKETS = ["futures"]` (`automation.py:214` (`PILOT_MARKETS = ["futures"]`)) — with state, log and kill switch under `data/live/pilot-futures/`.

The runner runs the setups in `docs/architecture/pilot-top20.json`, written by `scripts/rank-setups.py` from the stability backtests (`docs/backtests/2026-09-11-top-setups.md`): crypto setups on Binance futures TESTNET and CFD setups on the MT5 DEMO account through the file order bridge (`mt5-bridge.md`, `integrations/mt5/OrderBridge.mq5`). Each setup = (market, timeframe, rule family — ICT with a LIMIT at the FVG edge, or WYCKOFF-BOOK with a MARKET order at the entry bar's close (Spring reclaim, Test, BU) —, ICT target model, breakeven on/off, HTF filter on/off), applied function-for-function from `scripts/backtest-methods.py` to live candles (Binance private copies; MT5 export files, 2H aggregated from 1H): LIMIT at the FVG edge (post-only GTX on Binance; pending order with SL/TP on MT5), breakeven at +1R on a closed candle, time stop, one position or resting order per symbol, open positions capped per venue by that account's `max_positions` rule (`docs/architecture/account-profiles.json`, read through `scripts/account_profile.py`), halts per venue on −15 % equity / 5 losses and on 3 connector errors (writes the `STOP`).

**Risk and R:R are one decision, read through one reader each (user decision 2026-09-13; ceiling unified 2026-09-17).** Per-trade risk ceiling **1 %** — authored once in `docs/architecture/risk-config.json` `max_risk_pct` and read by one validated reader, `trading_env.MAX_RISK_PCT` (`trading_env.py:69` (`MAX_RISK_PCT = _read_max_risk_pct()`)), which refuses rather than guessing if the value is unreadable. Until 2026-09-17 this path carried its own literal 3 % while §7, §11, `risk-config.json`, RiskSkill, RiskAgent and `automation.py`'s own docstring all said 1 %: the automated pilot sized at three times what the human-confirmed `/execute` path enforced, and the SessionStart hook announced 3 % to every session. The runner reads it as `RISK_CEILING` and clamps `PILOT_RISK_PCT` to it (`strategy-runner.py:221-238` (`RISK_CEILING = trading_env.MAX_RISK_PCT`)). Planned-R:R floor **3.0** — one validated reader, `trading_env.min_rr()` (`trading_env.py:72` (`def min_rr(path=None):`)), sourced from `docs/architecture/analysis-params.json` `project_defined.ict.min_rr`; the runner takes it via `backtest-methods.MIN_RR` so the live path and the backtest cannot disagree (`strategy-runner.py:226` (`MIN_RR = bt.MIN_RR`)), and `backtest-methods.RISK` now reads the ceiling from the same place for the same reason. The floor is **unchanged** by the ceiling move, and the argument matters: under fixed-fractional sizing expectancy in R is scale-free in the risk fraction, so every R-multiple in the evidence still holds and only the absolute % return / drawdown columns scale — those must be re-run, not rescaled by eye. Evidence: `docs/backtests/2026-09-13-rr-floor-and-risk.md` (produced at 3 %).

**Selection.** A plain `/automation on|demo` selects **one setup per horizon per market** on the last 12 months (`rank-setups.py --horizons --window 1y`): one timeframe per horizon — scalping 15m, day 1H, swing 4H (`rank-setups.py:74` (`HORIZONS = {"scalping": "15m"`)), agreeing with `automation.HORIZON_TF` up to the `1h`/`1H` spelling. **`/automation on|demo setup top N`** instead runs `rank-setups.py --window 1y --n N` — every rule ranked on its last 365 days (not blown up → share of positive quarters in the year → the year's return → worst quarter; one row per timeframe × rule family) — writes the selection, records `execution.setup_spec` and brings everything up; the stability files carry both full-history and `w1y` metrics (`stability-report.py`). The loop period follows the fastest selected timeframe (`strategy-runner.py --tick-seconds`); setups whose backtest is negative are still included and flagged `negative_backtest: true` in the selection file — the user chose coverage over evidence there and the journal (`strategy` field) is how that choice gets measured.

It refuses to tick when the environment is `real`, when the automation gate is closed, or when the exchange shows a position/order it does not own (reconcile before new risk). Candles are fetched into the runner's private `data/live/pilot-futures/candles/` (`KLINES_OUT_DIR`), keeping §13 rule 3. Journal: `journal.py sync-pilot` ingests `top20-log.jsonl` with `strategy` / `htf_pass`. Threat model and 33 rules: `docs/security/2026-09-11-top20-pilot.md` — **nine of its rules cited the deleted engine as their enforcement point and are marked as needing re-derivation before `layers.pilot` is re-enabled**; parity evidence: `docs/backtests/2026-09-11-runner-parity.md`.

**Status of the edge (read before switching the profile on).** The backtests that motivated this profile contained a look-ahead in the ICT FVG rule (the gap could complete on the candle after the MSS and the limit "filled" at that candle's low). With the causal rule the 4-year edge is small: ICT 30m ≈ +9 %/yr with −31 % drawdown, ICT 1H ≈ +3 %, COMBINED 30m ≈ 0 (`docs/backtests/2026-09-11-stability-by-timeframe.md`). The machinery is built and verified on testnet; whether to run it is a separate decision recorded via `/improve`. **2026-09-12:** the ICT rule gained three deck-faithful switches (`ict_disp`, `ict_pd`, `std_origin` — displacement on the MSS candle, longs-from-discount / shorts-from-premium, STD fib-0 at the highest high before the sweep), all off by default; measured in `docs/backtests/2026-09-12-ict-deck-faithful.md`. The drawing layer and `ict-scan.py` now follow the page-verified geometry in `docs/audits/2026-09-12-ict-pdf-recheck.md` (OB open line + mean threshold, CISD, displacement flag, dealing range from the nearest BSL↔SSL pair, PDH/PDL, session highs/lows, OTE, STD projections). The `asia` session window is now 20:00–00:00 America/New_York (the decks' own Asia killzone), chosen by measurement over five candidate clocks (`scripts/asia-session-eval.py`, `docs/backtests/2026-09-12-asia-session.md`); `journal.py`'s session tag follows `session-model.md` with DST-aware local windows instead of fixed UTC hours.

## 10. Hooks — honest mapping to what Claude Code actually supports

The master spec's 7 "hooks" are a mix of two different things, and this design keeps them distinct rather than pretending all 7 are literal tool-call hooks:

- **Real Claude Code hooks (2 — one added after review):**
  1. `SessionFilterHook` → an actual `SessionStart` hook (`.claude/settings.json`) that reminds the assistant, at the start of every session in this project, of the hard safety rules, the instrument allowlist, and the per-trade risk ceiling -- the last two read LIVE from `instruments.json` and `risk-config.json` so the reminder cannot drift from what is enforced (it announced 3 % while every other reader said 1 %, until 2026-09-17).
  2. `PostDecisionJournalHook` (partial) → an actual `Stop` hook that prints a plain-text reminder at the end of every turn: *"If a TRADE/WAIT/NO_TRADE verdict was just produced, confirm it's recorded via `/journal`."* **Scoped honestly:** this is an unconditional nudge, not a verified enforcement gate — a Claude Code `Stop` hook shell command cannot reliably introspect "did this turn output a verdict" without fragile transcript-text matching, so this design does not pretend it can block a missed journal entry, only remind every single time. The real enforcement is still the workflow-embedded step below (every `/analyze` run's own procedure ends with a `trades/` write as a mandatory step) — the hook is a second-layer safety net, not the primary mechanism.
- **Workflow-embedded gates (the rest):** `PreAnalysisValidationHook`, `ConfidenceThresholdHook`, the full `PostDecisionJournalHook`, `InvalidationMonitorHook`, `PostTradeReviewHook`, `LearningUpdateHook` are implemented as explicit, mandatory steps inside the relevant Command/Skill/Agent (e.g., `/analyze`'s own procedure both opens with Data Validation and closes with "write to `trades/`" as literal numbered steps) rather than as separate harness hooks — Claude Code has no market-data-push or open-position-polling event to hook into, so a "monitor" hook is realistically a recommended periodic `/invalidate` call (optionally via the `loop` skill on a schedule the user chooses), not an automatic background trigger. Documenting this honestly avoids the "hidden state" / "unexplained scoring" anti-patterns the master spec itself warns against in §33.

## 11. Learning governance (unchanged from master spec, restated as an implementation note)

LearningAgent may propose changes to scoring weights, thresholds, or methodology rules, always via the `/improve` command's KEEP/TEST/ADOPT/REJECT template (master spec §31). It may **never** directly edit: the per-trade risk ceiling (`risk-config.json` `max_risk_pct`), the instrument allowlist, the stop-loss/invalidation requirements, or the Analysis≠Execution separation — those live in this document (§1, §7, §9) and in the hard-coded checks inside RiskAgent, not in data LearningAgent can rewrite. Any proposal touching those requires the human to edit this document directly.

## 12. Open items / explicit gaps (do not silently resolve these)

1. **No Heatmap source document** exists in `docs/` — HeatmapSkill's rules come only from the master prompt text, not from an ingested reference. If the user adds a Heatmap/liquidity book or course to `docs/`, ingest it before trusting HeatmapSkill's outputs at STRICT mode.
2. **CoinGlass is still MOCK** — no API key configured yet. Crypto market data itself is now LIVE (Binance connector, verified). The MT5 commodities bridge is **live and verified for XAUUSD** (2026-09-10; UTC timestamps, tick-volume caveat) — see `docs/architecture/mt5-bridge.md`; XAGUSD/USOIL/UKOIL need the EA attached to one chart each. No `/analyze` output using MOCK/untested sources can be treated as a live, tradeable signal; every such output must say so plainly.
3. **XAUUSD/XAGUSD/USOIL/UKOIL are structurally capped at NORMAL mode** even once the MT5 bridge is live and CoinGlass is connected — Footprint and Heatmap dimensions have no data source for commodities (CoinGlass is crypto-derivatives-only), so only Wyckoff + ICT (2 of 4 dimensions) can ever be engaged for these instruments in the current design. This is a structural limit, not a temporary gap — closing it would require finding or building a genuine order-flow/liquidity source for MT5 markets.
4. **Execution environments (user decision 2026-09-10).** The two Binance connectors — SPOT (`scripts/binance-testnet-order.sh`, LONG-only; file name kept for compatibility) and USDT-M FUTURES (`scripts/binance-futures-testnet-order.sh`, long/short, ISOLATED, leverage ≤ 3) — are **environment-driven**: endpoint and credentials come from `config/env.<environment>` through `scripts/trading-env.sh` / `scripts/trading_env.py`, where `<environment>` is `execution.environment` in `automation-config.json` (`demo` = testnet.binance.vision / testnet.binancefuture.com, fake funds; `real` = api.binance.com / fapi.binance.com, **real money**). `config/env.demo` points at the Keychain entries already in use; `config/env.real` ships with `__FILL_ME__` placeholders and every execution path refuses (exit 2) until they are replaced. Both files are gitignored; only `config/env.example` is committed. **MT5 execution remains unbuilt** — the env files carry MT5 account fields for a future connector, but today the MT5 side is data-only (item 6). Verification status: the environment refactor was written without being able to run it in the authoring session (the auto-mode classifier blocked Bash); `scripts/verify-automation-v3.sh` is the acceptance test to run before the first real tick.
5. **Account equity is user-supplied, not fetched** — RiskSkill has no live balance source in v1.
6. **CFD coverage is two symbols of four; the timeframe half of this gap is closed** (opened 2026-09-10; **re-checked against disk 2026-09-12**, and the original "XAUUSD only, 15m-and-slower" wording was stale on both counts). `integrations/mt5/ExportOHLCV.mq5` is still a **per-chart** EA (`g_symbol = _Symbol`, `ExportOHLCV.mq5:30`) — that is the structural limit — but it now exports **six timeframes per charted symbol: 1W / 1D / 4H / 1H / 15m / 5m** (`ExportOHLCV.mq5:70-75`), `InpBarsToExport = 600` (`ExportOHLCV.mq5:22`). Two consequences: (a) a symbol has **no data at all** until a chart running the EA is open for it. Verified on 2026-09-12 by listing `data/live/mt5-bridge/`: **XAUUSD and XAGUSD** are both exported, all six timeframes, 600 bars each and same-day fresh; **USOIL and UKOIL are still absent entirely**. This is why the scanner's `cfd-*` styles pass the enabled CFD instrument list explicitly and skip a symbol with no bridge file (`scan-loop.sh:84` (`if [ -s "data/live/mt5-bridge/ohlcv.`)). The automation config is a *separate* gate from the data: at that check `markets.cfd.instruments` still listed XAUUSD only, so XAGUSD has a live source that is not switched on (`python3 scripts/automation.py status`). (b) there is still **no M1 export**, so no 1m CFD style — and "no CFD scalping" is still false for a different reason: **since 2026-09-13 CFD scalping is `cfd-scalping` on 15m**, the same horizon table as crypto (§15.1), so `markets.cfd` carries `15m`/`1h`/`4h` timeframe keys and no `1m` or `5m` key. Note `analysis-params.json` `timing.min_timeframe_minutes` is `15` (`analysis-params.json:121`), which the 15m scalping window now exactly meets — before 2026-09-13 the 1m/5m pages existed but earned no killzone timing credit. Combined with item 3 (Footprint/Heatmap have no CFD source), this is why the v3 automation schema gives `markets.cfd` **no `1m` timeframe key and no `footprint`/`heatmap` dimension keys** (`additionalProperties: false`): the impossible states are absent from the shape rather than being flags that can be set and then silently ignored. Closing (a) for USOIL/UKOIL is operational — attach the EA to one chart per symbol; closing (b) for M1 would require a genuinely different export path.

### 9.x The unattended pilot loop (Stage 2; originally 2026-09-09, one engine since 2026-09-13)

**History, so the retired rules in `docs/security/2026-09-11-top20-pilot.md` stay readable.** From 2026-09-09 to
2026-09-13 this section described a *second, legacy* pilot script: a deterministic LONG-only 15m engine that ran on
Binance SPOT TESTNET and, from 2026-09-10, LONG/SHORT on USDT-M FUTURES TESTNET — a second rule set on the same
account. **That script and the `execution` profile key that selected it were both deleted on 2026-09-13** (user
decision: one engine; `docs/plans/2026-09-13-collapse-to-one-system.md`). Its rules are not carried here; where a
threat-model rule still cites it as an enforcement point, that rule is flagged as needing re-derivation.

**Current state.** `scripts/pilot-loop.sh` runs `scripts/strategy-runner.py --live` every tick and then
`scripts/journal.py all`; the tick period is the runner's own `--tick-seconds`, the loop period implied by the fastest
selected timeframe (`pilot-loop.sh:52` (`--tick-seconds`)). One venue, one directory, one STOP path:
`data/live/pilot-futures/` (`pilot-loop.sh:19` (`PD="$ROOT/data/live/pilot-futures"`)). `PILOT_MARKET` is gone — it
used to choose between the two engines, and once the second engine was deleted it selected only a state directory that
`/automation off` could not reach with a kill switch. Orders go through `scripts/binance-futures-testnet-order.sh`
(ISOLATED margin, leverage ≤ 3 — the connector refuses more) and, for CFD, `scripts/mt5-order-bridge.py`.
`strategy-runner.py --report` prints state, `--flatten` closes everything. Credentials come from the active
environment file (item 4 of §12; Keychain references by default); the assistant never sees them.

**Lifecycle (user decision 2026-09-10 — `/automation on|off` must behave like power on / power off):** `/automation on`
(or `demo` / `real`, which also set `execution.environment`) installs and bootstraps launchd agents — `com.tyme.trading.scanner`
and one pilot agent per venue in `automation.PILOT_MARKETS`, which since 2026-09-13 is exactly one, `com.tyme.trading.pilot.futures` (`automation.py:83` (`PILOT_LABEL = {"futures"`)) (KeepAlive, `PILOT_END=never`) — starts a
`caffeinate -dims` keep-awake, removes stale `STOP` files (on = re-arm), and reports whether the MT5 bridge is fresh (open
MetaTrader 5 first; CFD styles simply skip until it is). While the agents stay installed they also come back at login after a
reboot. `/automation off` writes the `STOP` files, boots the agents out **and deletes their plists** from `~/Library/LaunchAgents`,
and kills the keep-awake, so the machine is in the same state as after a shutdown. Every tick of the loop re-reads
`automation-config.json`, so flags flipped while it runs take effect on the **next tick** without a restart — the tick
period is no longer fixed at 15 min; it follows the fastest selected timeframe (`strategy-runner.py --tick-seconds`,
read by `pilot-loop.sh:52` (`--tick-seconds`)). `pilot start` refuses a
duplicate (a loop already running, including one started by hand, detected with `pgrep`) and an incomplete environment file.
The host must not sleep during the window: on 2026-09-10 a sleeping Mac froze the loop for 6 h, which is why `on` starts
`caffeinate`. `/execute` (manual, one confirmation) and this pilot (unattended) are the two execution paths; both trade the
active environment.

**What `on` does NOT cover by itself: the Claude-side chart layers.** The Sonnet local reads (layer 2), the daily full
analyses (layer 3) and the scalping publish tick are session crons (`CronCreate`, in-memory, 7-day expiry). Their
prompts are versioned in `integrations/crons/*.md`; `/automation on|demo|real` re-creates them in the current session
through `scripts/cron-templates.py` and `/automation off` deletes them (`.claude/commands/automation.md` steps 7–8).
They stop when the Claude session closes; the launchd scanner and the pilot do not. Moving these layers to launchd
(`claude -p` headless) is an open item, not done.

## 13. Three-layer market read and the "numbers from code" rule (2026-09-10)

The published chart artifacts are fed by three layers — deterministic scanner (đánh giá sơ bộ), Sonnet local read
(đánh giá cục bộ), and daily full analysis (đánh giá toàn diện). Cadences, files and the anchor/setup contract are
specified in `docs/architecture/data-sources.md` → "Chart refresh: three-layer read". Design rules that bind every
agent working on the charts:

1. **Numbers from code, words from the model.** Anchor comparisons, invalidation candles, premium/discount, EQ,
   entry/stop/target/R are computed by `scripts/ict-scan.py` into `data/live/prelim/<style>.facts.json`. Models quote
   those numbers; `scripts/check-model-prose.py` rejects prose whose numbers are not in the facts. Rationale: on
   2026-09-09/10 a Haiku bounded refresh compared price to the window range instead of the LPS anchor (wrong verdict
   for 9 h) and a Sonnet patch dated the invalidation before the anchor existed.
2. **The full analysis owns the anchors.** Whenever it changes the structure it must rewrite
   `data/live/anchors.<style>.json`; the scanner only compares.
3. **One writer per file.** The launchd scanner writes market data, prelim and scan state; publish ticks snapshot and
   read; the full analysis writes only its hand-off file (scalping) or the artifact (day-trade/swing).
4. **Full analysis is the daily picture, not the alert path.** Event-driven judgement is the Sonnet local read
   (1–2 min); the full analysis runs daily and on invalidation. On 2026-09-10 a 20-minute full analysis concluded a
   short setup that price had already invalidated by the time it was published.
5. **Background means outside the Claude session.** Scanner (`integrations/launchd/com.tyme.trading.scanner.plist`)
   and pilot loop survive session restarts; Claude does judgement and publishing only.

## 14. Model policy (user decision 2026-09-10)

**2026-09-11 (night) decision: no Haiku anywhere — every cron template and headless run pins Sonnet.** Historical rule kept for context: **Haiku displays; it never reasons.** Every step that analyses, scores, judges or maps an analysis into structured
fields runs on Sonnet or higher. Haiku is permitted for exactly one thing: relaying `scripts/automation.py` output
under `/automation`. This is enforced in files, not by convention:

1. **Agents pin their model.** Every analysis agent in `.claude/agents/` (`structure-agent`, `flow-agent`,
   `liquidity-agent`, `risk-agent`, `learning-agent`) carries `model: sonnet` in its frontmatter, so a dispatch from a
   Haiku session still runs on Sonnet. A new agent that reasons must pin a model; inheriting the session model is a bug.
2. **Reasoning commands carry a model gate.** `/analyze`, `/bias`, `/entry`, `/exit`, `/invalidate`, `/review`,
   `/improve`, `/risk`, `/journal` and `/status` open with the same instruction: if the session model is Haiku, do not
   run the procedure in-session; dispatch one `general-purpose` subagent with `model: sonnet` to run the command with
   the same arguments and relay its output verbatim. `/execute` instead stops and asks the user to switch with
   `/model`, because the one explicit human confirmation must occur in the same interactive turn as the model that
   prepared the order.
3. **`/automation` is display-only.** Haiku may run it. On a `!` warning or `REFUSED` it relays verbatim and suggests
   `/model sonnet`; it does not interpret.
4. **Background layers.** The scanner and the pilot are Python with no model. The local read (layer 2) and the full
   analysis (layer 3) are Sonnet agents (`data-sources.md`, three-layer table). Publish ticks may be Haiku because
   they copy, patch and publish; they do not judge (§13 rule 1 is what makes that safe).

Rationale: on 2026-09-09/10 a Haiku bounded refresh produced a wrong verdict for 9 h by comparing price to the
wrong reference (§13 rule 1). The cost saved by Haiku on the few display-only commands is small; the cost of a
misread in an analysis step is a trade.

## 15. Chart pages rendered from code; one method, one vocabulary (user decisions 2026-09-11)

The user's five requirements on the chart artifacts — (1) an overview window so past setups and their effect on the
present are visible, (2) volume on the Wyckoff chart and in the Wyckoff read, (3) layers 1/2/3 each split into
Wyckoff / ICT / Footprint / Heatmap and only then synthesised, (4) every method analysed and drawn with that method's
own knowledge and terms (Footprint may build on Wyckoff), (5) a trader-grade UI — are implemented as code, not prompts:

1. **`scripts/build-artifact.py <style>` renders every page.** Inputs: the scanner's candles (working + context
   window, both with volume), `prelim/<style>.facts.json` (layer 1, split per method by code), per-method
   `model.html` blocks (layer 2), `data/live/narrative/<style>.json` (layer 3, schema
   `schemas/narrative.schema.json`), `anchors.<style>.json` (levels tagged `method`). Models never touch HTML again.
2. **Method purity is enforced, not requested.** `scripts/method_purity.py` holds the term lists (project
   parameters); `check-model-prose.py`, `check-narrative.py` and the builder all refuse a Wyckoff block with ICT
   vocabulary, an ICT block with Wyckoff vocabulary or any volume word (§4.1 of `knowledge/integrated/method.md`: the ICT corpus has no
   volume), a Footprint block with ICT vocabulary. The synthesis block is the only place the de-duplication rule
   (`knowledge/integrated/method.md` §4.3) and the invalidation owner (§4.4) may be stated. Chart lanes follow the same rule: the
   Wyckoff lane draws price + volume + TR/phases/events, the ICT lane runs the price-only engine.
3. **Events by time, not index.** Narrative events/phases carry ISO candle times; the builder resolves indices at
   render time, so a sliding window can drop a label but never move it onto the wrong candle.
4. **Context reuse.** A style whose working window is another style's context window (`scalping` 15m ↔ `day` 1h,
   `day` 1h ↔ `swing` 4h, and the `cfd-` pair of each) reuses that narrative for its context chart (`CTX_REUSE`), so two
   pages never disagree on the same candle series. Which style sits above which comes from the ladder, not from a
   second table: `automation.py:193` (`TIERS[_style] = {k: ({"tf": t, "style"`). Context numbers come from that style's own scanner facts (`local-eval-brief.py <ctx-style>`).
5. **Manual reads while automation is off.** `local-eval-brief.py --manual` bypasses the `/automation` gate for a
   user-requested one-off read; crons never pass it. The switch itself is never flipped by an analysis.

6. **Wyckoff phase grammar is code (2026-09-11, after ETH was labelled A→C→D).** `check-narrative.py` refuses a
   narrative whose phases are not contiguous from A in time order, whose event labels are not Wyckoff event names in
   their own phase, whose Phase C has no test event or Phase D no SOS/LPS, or whose "SOS" sits on below-average
   volume (WA p83–84 defines SOS by widening spread *and* rising volume; a weak break above AR is UA). The book's
   vocabulary is the validator, not the model's memory.

7. **The chart layer is TradingView's open-source Lightweight Charts, vendored (user decision 2026-09-12;
   `docs/specs/2026-09-12-chart-lightweight-charts-design.md`).** `scripts/vendor/lightweight-charts.standalone.production.js`
   (5.2.1, Apache-2.0, pinned, inlined at build — no CDN) draws candles, volume, axes, crosshair and owns every
   interaction (kinetic drag, wheel/pinch zoom, axis drag). `scripts/chart.js` holds everything the project adds as a
   list of shapes in (bar index, price) space rendered by one series primitive: the price-only ICT engine, Wyckoff
   TR/phases/events, anchors, the trade plans from `trades/index.jsonl` (PLANNED/OPEN, read-only) and the narrative's
   invalidation level, plus two per-chart modes that persist nothing — the R:R ruler (`R`) and bar replay (`P`, engine on
   the prefix up to the cursor, no future leak). Engines run once per tier window, never per zoom, so overlays match the
   scanner facts. Data sources are unchanged (Binance / MT5 bridge); the library never fetches. The journal's R curve
   uses the same build. Attribution (Apache-2.0 §4(d) + the library's NOTICE): the on-canvas logo is off and every page's
   footer prints the NOTICE line with the TradingView link — a test pins both halves. Tests: `scripts/tests/test_build_artifact.py`,
   `test_journal_render.py`.

Retired 2026-09-11 (deleted from the tree; named here only so an older commit message still resolves):
`patch-arrays.py`, `inject-prelim.py`, `select-base.py`, the hand-off file `narrative/<style>.full.html`.

### 15.1 CFD timeframe set (user decision 2026-09-11; collapsed onto the crypto horizons 2026-09-13)

MT5 offers M1…W1. **Since 2026-09-13 CFD runs the same three horizons as crypto and nothing else** — `cfd-scalping`
15m · `cfd-day` 1h · `cfd-swing` 4h — because there is one authored horizon table for both markets
(`automation.py:142` (`HORIZON_TF = {"scalping": "15m"`)) and the scanned set is `15m`/`1h`/`4h` per market
(`automation.py:115` (`MARKET_TIMEFRAMES = {m: list(_SCANNED_TF)`)). `1D` and `1W` remain as **context rungs**: fetched for the
chart, never scanned (`automation.py:188` (`PAGE_RUNGS = {m: _SCANNED_TF`)). The tiers above each window come from the
ladder in `timeframe-mapping.md` §5, which is generated from `automation.TIERS`.

Withdrawn earlier claims, kept as a record of why the set is what it is: the 2026-09-11 M5 CFD scalping window
(`5m×288 = 24 h`) went away with `5m` on 2026-09-13; "M1 is rejected for XAUUSD — the spread swallows a 1-minute bar"
stays **unverified** (the repo holds no 1m XAUUSD data to measure it; `timeframe-mapping.md` row E) but is moot while
no CFD sub-15m style exists; and "M30 adds nothing between M15 and H1" was **withdrawn 2026-09-12**
(`timeframe-mapping.md` row D) — the 2026-09-13 decision resolved it the other way, by giving `day` exactly one
timeframe, `1h`, rather than adding a 30m style.

The EA must export 15m/1H/4H plus 1D and 1W for the context rungs (`integrations/mt5/ExportOHLCV.mq5`); it exports
1W/1D/4H/1H/15m/5m today, so every scanned CFD rung has a source. This supersedes the "no CFD scalping" note in §12
item 6; `markets.cfd.timeframes.15m` is the switch.

### 15.2 Multi-timeframe: the "giảm khung" rule is code (user decision 2026-09-11)

The book reads the higher timeframe first and enters on the lower timeframe in the direction of the higher-timeframe
structure (`knowledge/wyckoff/advance.md` §2.7 "Giảm khung của tích lũy", WA p93–96: M30 Shakeout[C] → m5 Spring[C]/LPS[C]; in Phase B
"nguồn cung/cầu đang khá cân bằng … chưa cho thấy sự xuất hiện của CO" — no trade; `knowledge/integrated/method.md` §4.2 step 1). Implemented as:

1. **One rule, one table** — `scripts/automation.py` `next_rung` / `TIERS` (2026-09-12, replacing the hand-written `CONTEXT_STYLE`):
   each style has three tiers, Vào lệnh (its own window) → Cấu trúc → Bias, adjacent tiers being the next available rung
   ≥ ×4 (`docs/architecture/timeframe-mapping.md` §3; the rule reproduces the pilot's `HTF_OF` exactly, pinned by
   `scripts/tests/test_timeframe_ladder.py`). The **gate** tier (`gate_style`) — bias when it has a scanned style, else
   structure — is what `CONTEXT_STYLE` now aliases; the checkers and the pilot filter read it. Pages draw all three tiers
   for both Wyckoff and ICT (ladder block + three charts, top-down).
   `scripts/strategy-runner.py` / `scripts/backtest-methods.py` derive `HTF_OF` (the structure tier over the runner's rungs)
   from the same function, so no second table exists.
2. **Scanner facts carry the context** (`facts.json` → `symbols.<SYM>.context`, written by `scripts/htf_context.py`
   from the context style's own facts plus the latest Wyckoff structure/phase of that window) and a **bias**:
   accumulation/re-accumulation in Phase C/D/E → long; distribution/re-distribution in C/D/E → short; **Phase B →
   directional only at the boundary of the higher-timeframe Trading Range in the direction of the structure**
   (accumulation with price in the lower third of the TR → long — "CO sẽ tiếp tục tích lũy khi giá tiệm cận vùng hỗ
   trợ", WA p201, and the m5 "Local accumulation as Spring" of WA p93; distribution in the upper third → short;
   mid-range or the opposite boundary → neutral, WA p95–96); Phase A or "chưa xác lập" → neutral; no read → the
   context scanner's anchor verdict, else unknown. The "third" is the book's ST-within-⅓-TR yardstick reused as the
   zone width (project adaptation, `BOUNDARY_FRACTION` in `scripts/htf_context.py`). User question 2026-09-11: a
   lower-timeframe reversal *at* the higher-timeframe range edge, in the structure's direction, is exactly the book's
   drop-down trade — it is allowed; a reversal *against* the higher-timeframe trend is "bắt dao rơi / cản tàu" (§2.4)
   and stays refused until the higher timeframe prints its own CHoCH.
3. **Layer 2** sees a "BỐI CẢNH" section in its brief; `m-synth` must open with "Bối cảnh <tf>: …"; a verdict
   against the bias must say "ngược bối cảnh"; SETUP TIỀM NĂNG against the bias or while the context is in Phase
   A/B is refused (`check-model-prose.py`). **Layer 3**: `context.wyckoff` (structure + phase + cited text) and
   `context.ict` are mandatory when a context window exists; the same verdict rule applies to `synthesis_html`
   (`check-narrative.py`).
4. **Pilot** (`scripts/strategy-runner.py`): the higher-timeframe read is computed for every signal and logged as
   `htf_pass` (`strategy-runner.py:962` (`def htf_pass(sym, side, candles_htf, htf_tf):`)); a setup carrying
   `htf: true` refuses the order unless that read equals the side — **including when the read is `None`**, i.e. the
   bias could not be determined (`strategy-runner.py:1902` (`if st.get("htf") and sig["htf_pass"] is not True:`)),
   which is the WA p95–96 "neutral/unknown refuses too" rule. The tier used is the **structure** tier over the
   runner's own rungs, `HTF_OF` (`strategy-runner.py:157` (`HTF_OF = {tf: _auto.next_rung(`)) — the same `next_rung`
   function as item 1, not a second table. This was a trading-rule change the user adopted directly on 2026-09-11
   instead of running it through `/improve` TEST first — recorded here so `/improve` can measure it against the eval
   log. (Until 2026-09-13 this item described the deleted engine's fixed 4H `HTF_FILTER`.)

Pages show the context bias in each symbol header and in the Sơ bộ synthesis cell.

### 15.3 Every published page is bilingual EN / VI, English by default (user decision 2026-09-17)

Design: `docs/specs/2026-09-17-artifact-i18n-design.md`. The three page families — the chart artifacts, the
method control panel, the trade journal — carry an **EN / VI toggle, English default**, and the displayed
timezone follows the language (EN → UTC, VI → VNT, UTC+7). The rules that matter here:

1. **Three kinds of text, three rules.** *Chrome* written by a renderer is bilingual, from the one catalog
   `docs/architecture/i18n.json` (reader: `scripts/i18n.py`, the only one). *Machine values* — the narrative
   verdict enum, the structure words `htf_context.py` matches to decide bias direction, symbols, methodology
   names, acronyms, config keys — are never translated anywhere they are stored or matched; they get a display
   label and nothing more. *Authored prose* — the layer-2/3 model blocks, anchor labels, the journal's review
   fields — is shown verbatim and marked (`i18n.vi_source`), never machine-translated: translating an analysis
   would change the analysis. Registry display text (`methods.json` `reads`, `pane.label`, preset `label`) stays
   in its registry, now as `{en, vi}`.
2. **The switch is presentation, and that is enforced, not asserted.** Each fragment is rendered once per locale
   into `lang`-tagged siblings and one CSS rule shows one; the wrapper wraps CONTENT, never structure, because
   the `.matrix`/`.ladder` grids place cells with `grid-template-columns`. `scripts/tests/test_i18n.py` proves
   every number is byte-identical between the locales of one built page, that no unmarked Vietnamese is visible
   in English mode (and no English sentence in Vietnamese mode), and that the session/killzone conversion — which
   uses real IANA zones and follows DST — never reads the display locale. Numerals stay `en-US` in both
   languages on purpose: two renderings of one price on one screen is a misreading risk with no upside.
3. **Method purity now runs in both languages.** The build gate (`method_purity.py`) sees both locales of every
   layer-1 block because the page carries both; the glossary, ladder, legend and bias basis, which the gate never
   reached in *any* language, are checked by `test_i18n.py` instead. The English wording is where this is easy to
   get wrong — "markup" and "trading range" are Wyckoff terms an ICT sentence reaches for naturally, "sweep" is a
   liquidity word a Wyckoff sentence reaches for naturally.
4. **`htf_context`'s bias basis travels as data** — `(tag, message key, params)` — because it has two audiences:
   the page, in the reader's language, and the model brief, in the language the model authors in
   (`i18n.AUTHORED`). The `bias` value itself, which gates a trade, is untouched by any of this.
5. **The panel's language never reaches the `db`.** Those rows are the control plane
   (`docs/security/2026-09-12-method-panel.md` PANEL-01); a per-viewer preference lives in `localStorage`.
   PANEL-02's disclosure is printed in whichever language the reader chose, both locales in the markup.
6. **Artifact `<title>`s stay as first published** — identity in the gallery, expected stable across redeploys —
   and the shim retitles the browser tab per language instead.

7. **Runtime-written text repaints on the switch.** Chrome that exists once in the DOM because it is written
   at interaction time — the chart's R:R-ruler and bar-replay status line, the panel's request status, pending
   notes, stall and db banners, the journal chart's time axis — cannot be a `lang` sibling. Each stores a
   *message key* rather than finished text and repaints from a `data-lang` MutationObserver; a param named
   `*_key` is resolved at paint time so one language's word is never frozen inside another's sentence.
8. **Numerals are declared, not assumed.** Every locale record carries `number_locale`, and both `i18n.num()`
   and the two chart runtimes read it. All locales declare `en-US` today — which is *why* the numbers are
   byte-identical across the switch, a fact stated by the data rather than baked into the formatters.
9. **`context.basis` in `facts.json` is versioned** (`htf_context.BASIS_FORMAT`). Format 1 was a rendered
   sentence; format 2 is the keyed list. Format-1 snapshots stay on disk and stay readable — `basis_text()`
   returns a string basis unchanged — and nothing reads the stored value to make a decision, so no data
   migration is required (CLAUDE.md §59).

**Known limitation: the language choice does not travel between the three artifacts.** Persistence is
`localStorage['artifact-lang']`, and each artifact is served from its own origin, so storage never crosses
between them. Nothing links one artifact to another today, so no in-product navigation loses the choice; a
`?lang=` link does carry it, and is now remembered rather than honoured once.

**Still Vietnamese-only: the model-authored analysis prose.** Phase 2 (specified in the design doc, not built)
moves the model contract to bilingual authoring. Until then an English reader gets the conclusions in English
and the reasoning in Vietnamese, marked; the page says so on its face. `publish-plan.py` counts `i18n.json` and
`i18n.py` as page inputs, so a translation fix marks every page due.

## 16. Providers are data, not paths (CLAUDE.md §2, 2026-09-18)

`CLAUDE.md` §2 requires the architecture to be provider-agnostic and states the rule bluntly: *Binance must
not become the architectural center*, and market-data / analytics / aggregated-intelligence / execution must
be **independently** choosable. Before this section the repo failed that in a specific, checkable way —
`scripts/strategy-runner.py` carried its connectors as module constants, so choosing a different venue meant
editing the live order engine, and `markets.<m>.feed` in `instruments.json` was prose no code could dispatch
on.

**`docs/architecture/providers.json` is now the single source for provider identity**, with
`scripts/providers.py` as its only reader — the same one-registry-one-reader-one-drift-test discipline §1 uses
for the instrument allowlist and §6.2 uses for the method registry. Six providers are declared today; read the
file, do not restate them here.

What the registry makes checkable, and what it deliberately does not:

1. **Four roles, asked independently.** `P.for_role("market_data", "crypto")` and
   `P.for_role("execution", "crypto")` are different questions with different answers — that *is* §4's
   "Data Source != Execution Venue", expressed as a query rather than trusted as a convention. A provider
   holds a list of roles, so `mt5_bridge` can supply CFD data and receive CFD orders through two different
   programs without the two being one field.
2. **A claim must be callable.** Loading refuses a declared adapter that is not on disk, and refuses any
   provider claiming the `execution` role with no adapter — "can receive orders" is the one claim that may
   never be decorative. Fail-loud at import, matching `trading_env.py`'s refuse-don't-guess reader.
3. **Status is truthful.** `connected` / `mock_only` / `not_built`. CoinGlass is `mock_only` (no key), so
   `providers.is_live("coinglass")` is False and it may not satisfy a live decision requirement — the same
   rule §6.1's engaged-dimension gate already applies to data sources.
4. **`external` scopes the hard-coding ban.** The repo's own scanner is declared as the `local_derived`
   analytics provider, because §2 wants the analytics choice to be visible rather than implicit — but it is
   not a vendor, and sibling modules may load it by name (`scripts/live_rules.py:34` (`ict_scan = _load(`)
   does, correctly). The ban on hard-coding a connector path applies to external providers only.

### 16.1 Routing: what moved to data, and what is still a branch (CLAUDE.md §4)

`CLAUDE.md` §4's operative rule is its last sentence — *never couple the Decision Engine directly to a
specific exchange* — not "no code may branch on a venue". An adapter is allowed to know its venue; that is
what an adapter is. So §4 is split into the part that is a defect and the part that is design.

**Closed — where an order goes is resolved from data.** `venue_of()` was
`"futures" if sym in CRYPTO else "mt5"`: a symbol-membership test that hard-coded the market→venue mapping
inside the order engine, and whose `else` was **fail-open** — any symbol the engine did not recognise (a typo,
or one removed from the allowlist) resolved to the MT5 venue instead of refusing. It now reads the market from
the instrument allowlist and the venue from the provider registry, and raises on an unknown symbol
(`strategy-runner.py:1519` (`def venue_of(sym):`)). Every allowlisted symbol resolves exactly as before —
pinned symbol by symbol in `scripts/tests/test_execution_router.py:45` (`def test_every_allowlisted_symbol`).

**Closed — a human-confirmation venue can no longer be selected by a loop with no human in it.** Execution
providers declare `execution_alias` and `unattended`. `binance_spot` is `/execute`'s venue and its entire
safety story is one explicit human confirmation per trade, so it is `unattended: false` and
`providers.unattended_venue_for()` will never hand it to the pilot. That function also refuses rather than
guesses when a market has zero or several unattended providers (CLAUDE.md §6: no silent provider switching).

**Closed — the Decision Engine names no exchange.** `scripts/live_rules.py`, the layer both the live runner
and the backtest read their setups through, contains none of `binance` / `mt5` / `coinglass` / `venue` /
`exchange`, and its functions take candles rather than a symbol or a venue. This matters beyond tidiness: a
decision that could differ by venue would mean the backtest had stopped measuring the thing that trades.

**Still a branch, deliberately.** Order *submission* remains venue-shaped — a post-only GTX limit on Binance
futures and a pending order with attached SL/TP on MT5 are different operations, at roughly a dozen sites.
Flattening them into one `submit()` would be a rewrite of the engine that sends real orders, for no §4
benefit. The one pure-dispatch case was converted (`VENUE_LOG`, the per-venue log destination) to show the
shape a real router would take.

**Closed 2026-09-18 at §33.** `MAX_OPEN` used to be keyed by venue as `{"futures": len(CRYPTO), "mt5":
len(CFD)}`, but two markets (cfd and forex) route to the `mt5` venue, so the cap bounded the combined book at
the CFD count. It was *conservative* rather than wrong, and deriving it from the registry would have *raised*
a risk cap as a side effect of a refactor — which `CLAUDE.md` §59 is explicit about not doing silently. It is
now the `max_positions` rule of the MT5 account's profile (`docs/architecture/account-profiles.json`), derived
across every market routed to that venue, as a deliberate account-rule decision rather than a refactor
side effect. Binding effect today is unchanged: no FX order can be placed (no FX setup exists in
`pilot-top20.json`, `markets.forex.default_enabled` is false) and one-position-per-symbol still dominates.

Tracked in `docs/architecture/SPEC-COMPLIANCE.md` §4.

## 17. Domain layers → artifacts (CLAUDE.md §3, 2026-09-18)

`CLAUDE.md` §3 names two flows — a conceptual one (Market → … → Performance & Ranking) and a technical one
(Provider Adapters → … → Execution Provider) — and closes with a rule: **do not collapse these concepts into a
generic "strategy" abstraction.** The layers are not restated here; read §3. What this table adds is the thing
§3 cannot state about *this* repo: which layer has an artifact, and which is currently being done by something
else wearing its hat.

`scripts/tests/test_domain_layers.py` parses both flows out of `CLAUDE.md` §3 and fails if any layer has no row
here, or if a row claims an artifact at a path that does not exist. A layer with no artifact must say so — the
one thing not allowed is a layer quietly vanishing from the map.

| Layer (CLAUDE.md §3) | Artifact today | State |
|---|---|---|
| Market | `docs/architecture/instruments.json` `markets` → `scripts/instruments.py` | Present |
| Instrument / Market Type | `instruments.json` `analysis`/`execution` lists → `scripts/instruments.py` | **Half.** Instrument identity is present and enforced; **Market Type (SPOT/FUTURES/PERPETUAL/CFD/OTHER) does not exist** — CLAUDE.md §5. |
| Session | `docs/architecture/sessions.json` (THE registry), read by `scripts/sessions.py`; `scripts/journal.py:161` (`def session_of`) delegates and `scripts/chart.js:27` (`const SESSIONS`) is generated by `scripts/sync-sessions.py` | **Registered 2026-09-18.** One source, one reader, one generator, drift-tested. Overlaps resolve by declared precedence; `version` makes a window change visible to a configuration snapshot — CLAUDE.md §21. |
| Data Sources / Provider Adapters | `docs/architecture/providers.json` → `scripts/providers.py` | Present (§16). Identity only; routing is §4. |
| Normalized Data Layer | `docs/architecture/data-sources.md` contract; writers `scripts/fetch-binance-klines.sh`, `integrations/mt5/ExportOHLCV.mq5` | **Partial.** One normalized OHLCV shape exists; 9 of the 15 provenance fields CLAUDE.md §7 requires are absent, including `available_time`. |
| Derived Analytics | `scripts/ict-scan.py`, `scripts/wyckoff_rules.py`, `scripts/htf_context.py` → `data/live/prelim/<style>.facts.json` | Present. Numbers from code, words from the model (§13 rule 1). |
| Evidence | `scripts/evidence.py` (THE record type) | **Built.** An observation carries source, methodology scope, `event_time`, `available_time` (derived from the bar via §7/§8) and a quality inherited from the source series rather than asserted; `E.admissible()` is §8's gate applied per observation. Stale claim removed 2026-09-18. |
| Methodologies | `docs/architecture/methods.json` → `scripts/methods.py`; theory in `knowledge/`; purity enforced by `scripts/method_purity.py` | Present. |
| Setup / Setups | `docs/architecture/pilot-top20.json`; live detectors in `scripts/live_rules.py` | **Partial and overloaded** — see the collapse note below. Unversioned (CLAUDE.md §14). |
| Custom Rules / Constraints | `docs/architecture/automation-config.json` (dimension/timeframe/instrument flags), `docs/architecture/analysis-params.json` (thresholds) | **Partial.** Constraints exist as global switches; there is no per-Trading-System custom-constraint object. |
| Event Risk / News | `docs/architecture/event-calendar.json` (registry, snapshotted); reader `scripts/event_risk.py` | **Built 2026-09-18** — per-instrument relevance, point-in-time visibility, unioned windows, configurable buffers, fail-closed. See §40. The calendar still has no automatic feed and is hand-maintained; `covers_through` is what makes that state visible instead of silent. |
| Risk Model | `docs/architecture/risk-config.json` → `scripts/trading_env.py:69` (`MAX_RISK_PCT = _read_max_risk_pct()`) | **Present for the ceiling.** Fees and slippage are absent from live sizing — CLAUDE.md §34. |
| Account Profile | `docs/architecture/account-profiles.json` → `scripts/account_profile.py` | **Built 2026-09-18 (§33).** Two profiles (`pilot-binance-futures-testnet`, `pilot-mt5-demo`), each declaring all sixteen rule keys; the runner's hard-coded constants now read through `profile(venue)` and a venue with no declared rules refuses to trade. Stale claim removed 2026-09-18. |
| Trading System | `docs/architecture/trading-systems.json` → `scripts/trading_system.py` | **Built 2026-09-18** — one system per style (`automation.STYLE`, refused if the key sets differ), composition resolved from the owning registries rather than copied, and §35's four-way dependency classification declared and enforced: required-ness cannot be inherited, unknown context resolves REQUIRED, and only `REQUIRED_FOR_DECISION` may gate. See §43. |
| Decision Engine | `docs/architecture/decision-order.json` (THE canonical 17 steps) → `scripts/decision_order.py`; walked by `scripts/strategy-runner.py` `tick()` and by `.claude/commands/analyze.md` | **Built 2026-09-18.** One artifact both paths are measured against; each step declares where it lives on each path or why it is absent. Every live decision records a `decision_trace` that refuses to go backwards, to block where blocking is forbidden, or to place an order after a block. See §44. |
| Execution Router | `scripts/strategy-runner.py` `venue_of()` → `scripts/providers.py` `unattended_venue_for()`; `VENUE_LOG` lookup | **Partial, and no longer fail-open.** The market→venue resolution is data (an unknown symbol *refuses* instead of defaulting to MT5, which is what the old `else` did), and the log destination is a lookup. **6 `if venue == "mt5"` branches remain** at the order-shape boundary — down from ~12 — and that is the adapter boundary by design (§16.1), not the routing decision. Count corrected 2026-09-18. |
| Execution Provider | `providers.json` `execution` role → `scripts/binance-testnet-order.sh`, `scripts/binance-futures-testnet-order.sh`, `scripts/mt5-order-bridge.py` | Present. |
| Backtest / OOS / Walk Forward | `scripts/backtest-methods.py`, `scripts/stability-report.py`; `docs/architecture/validation.json` → `scripts/validation.py`; `docs/architecture/research-ledger.json` → `scripts/research_ledger.py` | **Built 2026-09-18 (§44, §45).** All twelve §45 methods exist including `oos` (which consults the §44 ledger and never invokes the evaluator on development data) and `walk_forward`. **What they report is the finding:** no period in this repository is untouched, so `oos()` refuses rather than passes — true before this existed and invisible. |
| Performance & Ranking | `docs/architecture/performance-metrics.json` → `scripts/performance.py`; `docs/architecture/ranking.json` → `scripts/ranking.py`; `scripts/journal.py` `stats()`, `scripts/rank-setups.py` | **Built 2026-09-18 (§39, §48).** All 23 §39 metrics with a `min_n` each and `unavailable()` as a value that sorts; seven configurable ranking objectives, all **lexicographic** — `refuse_universal_score()` exists only to raise. Sample size is still always shown. |

### 17.1 The collapse §3 warns about is real here, and it has a name

§3's closing rule is *do not collapse these concepts into a generic "strategy" abstraction*. This repo has not
collapsed **methodology** into strategy — `methods.json` keeps dimensions, modes and presets separate from
setups, and `method_purity.py` enforces the vocabulary boundary. But one collapse does exist:

a row in `docs/architecture/pilot-top20.json` is `(market, timeframe, rule family, target model, breakeven,
HTF filter, execution venue)` in a single object. That tuple is not a Setup — a Setup is *the market condition
that qualifies for entry*. It is a **Trading System** minus its account profile, risk model and event-risk
rules, which is why CLAUDE.md §35's dependency declaration has nowhere to live today and why `trade-file`
records `strategy` as a free string. The fix is not to rename the file; it is to give Trading System its own
artifact (§35) and let the setup row shrink back to the entry condition it should always have been.

**Half fixed, 2026-09-18 (§43).** Trading System now has its own artifact, and the part of the tuple that was
never the setup's — account profile, risk model, event-risk rules, and above all the dependency
classification — has moved out of the row and into `trading-systems.json`, which finds a row by its
`(market, horizon)` rather than the row carrying the system inside it. What has **not** changed is the row
itself: it still carries `execution`, `fee_assumed` and `mgmt` alongside the entry condition, so a setup is
still a slightly-too-large object. Shrinking it is a `pilot-top20.json` schema change with a `rank-setups.py`
writer and a §47 version question attached, and it belongs there rather than here.

## 18. The canonical market model (CLAUDE.md §5, 2026-09-18)

`CLAUDE.md` §5 asks for a provider-independent market model and forbids one specific thing: *do not use
provider-specific market terminology as the canonical domain identity.* This repo had a live instance of that
hazard, and closing §5 is mostly about naming it.

**Two vocabularies, deliberately separate.** Read the registries, not this list:

| Concept | Where declared | Answers |
|---|---|---|
| **Market type** — `SPOT` / `FUTURES` / `PERPETUAL` / `CFD` / `OTHER` | vocabulary in `docs/architecture/instruments.json` `market_types`; the type of an actual contract on `docs/architecture/providers.json` `providers.<p>.market_type` | *What is this contract?* — does it expire, does it pay funding, whose contract specs apply |
| **Venue alias** — `spot` / `futures` / `mt5` | `providers.json` `providers.<p>.execution_alias` | *Where does the order go?* — and what state rows, logs and setup `execution` fields are tagged with |

**The hazard, stated plainly.** Binance calls its USDT-M product "futures", and every state row, log line,
setup `execution` field and pilot directory in this repo carries that word. The contract has no expiry and
pays funding: it is a **PERPETUAL**. So the venue alias `futures` *looks* like the canonical `FUTURES` market
type and is not one. The alias cannot be renamed without migrating persisted state, so the collision is
**declared at the point of definition** (`providers.json` → `binance_futures.alias_collides_with_market_type`)
and `scripts/tests/test_canonical_market_model.py` fails if that declaration is removed, or if a second
misleading alias appears. Code that reasons about funding, expiry or settlement calls
`providers.market_type_of()`; code that reads a state row uses the alias. They are never the same field.

**Market type is a property of (instrument, venue), not of the instrument.** `BTCUSDT` is SPOT on
`binance_spot` and PERPETUAL on `binance_futures`. A per-symbol `market_type` — the obvious first design, and
the one the compliance audit proposed — would have to pick one and be wrong about the other. So a *market*
declares which types it can hold (`crypto: ["SPOT", "PERPETUAL"]`) and an *execution provider* declares the
one type a contract on it is; loading refuses a provider offering a type its market does not declare.

**Canonical instrument identity.** `docs/architecture/instruments.json` `canonical` maps each provider
spelling to a provider-independent id — `BTCUSDT` → `BTC/USDT`, and `USOIL`/`UKOIL` → `WTI/USD`/`BRENT/USD`,
naming the benchmark rather than the MT5 broker's ticker. Loading requires every analysable symbol to have one
and refuses duplicates (two symbols sharing an identity would merge two instruments' history the first time
anything grouped by it). Identity is kept out of `display()` on purpose: a label is presentation and may be
restyled, an identity may not, and one field doing both jobs means a styling edit silently re-identifies an
instrument. `canonical` is what `CLAUDE.md` §7's `canonicalSymbol` provenance field will carry.

**Not done here: CFD account/context types** (Personal / Prop Challenge / Prop Funded / Demo / Custom). §5
mentions them, but they are account rules and belong to the Account Profile object (`CLAUDE.md` §33);
building half an account model inside the market model would put account rules in two places. A test asserts
they have *not* quietly appeared in `instruments.py`, so the gap stays visible.

## 19. Provider capabilities: declared, live, and the difference (CLAUDE.md §6, 2026-09-18)

`docs/architecture/providers.json` `capabilities` is the vocabulary; each provider declares what it actually
supplies. Read the file for the list. What matters here is the rule set §6 imposes and how each is held.

**Explicit, never assumed.** A provider with no `capabilities` list refuses to load — "none" is written `[]`.
A capability outside the vocabulary refuses to load, so one cannot be conjured at a call site. The `execution`
role and the `order_submission` capability must agree.

**Declared ≠ live, and that distinction is the point.** CoinGlass *declares* footprint bars, liquidation and
orderbook heatmaps, OI and funding — and has no API key, so its status is `mock_only`.
`providers.providers_with(cap, market, live_only=True)` is the live question;
`markets_with_capability(cap)` is the structural one. `methods.live_sourced(dim, market)` answers it per
Confluence dimension.

**The trap this closed.** `methods.dispatch_plan()` has always accepted an `unavailable` set — and **nothing
in production ever passed one** (only a test did). So under the `full` preset, the CoinGlass-backed Footprint
and Heatmap dimensions would have been reported `engaged` and counted toward `engaged_count` with no API key
configured: a fixture satisfying a live decision requirement, which §6.1 forbids by name. It was not reachable
on the live config (preset `ict`), but it was one preset change away.
`scripts/tests/test_capabilities.py::DeclaredIsNotLive` pins it. **Gating** a decision on this is `CLAUDE.md`
§36 work and is not claimed here — what §6 closes is that the state is now computable and carries its reason.

**Unavailability preserves its cause.** `providers.capability_report()` distinguishes three cases that must
not read alike, because they are different answers to "should I wait?": live (names the providers); a source
exists but is not connected (names which, and its status); no provider supplies it here at all.

**Five capabilities no provider declares** — `ohlcv_realtime`, `trades_raw`, `orderbook_depth`,
`economic_calendar`, `news`. Deliberate, and pinned by a test. That is the registry stating in a
machine-readable place that this system has no realtime feed (§52), no raw trades to build a footprint from
(§22), and no calendar feed (§24–§32) — the root cause of those gaps, written where code can see it.

**A dimension's markets are now derived, not asserted.** `methods.json` `dimensions.<d>.markets[]` stays
authored, but loading fails if it differs from what the providers supplying that dimension's capabilities
actually cover. The dimension's `data_sources` moved from vendor names (`coinglass_footprint`) to capability
ids (`footprint_bars`), which also removed the last vendor coupling from the page builder — it used to decide
"is this dimension CoinGlass-backed?" by prefix-matching the string `coinglass_`.

## 20. Normalized data and provenance (CLAUDE.md §7, 2026-09-18)

`scripts/normalized.py` is the normalized data layer. `N.load(symbol, timeframe)` returns the candles as
written plus a provenance record carrying every field `CLAUDE.md` §7 requires. Read the module for the field
list; what belongs here is why it is shaped this way.

**Provenance is derived, not copied.** The obvious implementation — write all fifteen fields into every OHLCV
file — was rejected twice over. The writers are a bash script and an MQL5 expert advisor that only recompiles
inside MetaTrader, so half the fields could not be added without the user rebuilding an EA. More importantly,
`provider`, `source_venue`, `market_type`, `canonical_symbol`, `aggregation_scope` and `underlying_venues` are
facts about the **registry**, not about a file of candles: copying them into 131 data files would create 131
copies of what `providers.json` already owns. The file keeps its small header (`symbol`, `timeframe`,
`last_updated`, `_source`); the layer joins it to the registries. `_source` is matched through
`providers.by_source_marker()`, so a third feed is a registry entry rather than an edit to a loader.

**`available_time()` is the load-bearing function.** A bar with open time T on timeframe D is knowable at T+D
and not one second earlier; reading its close at its open time is the commonest look-ahead there is. The live
engine already enforced exactly this as an inline expression inside `drop_forming()`
(`strategy-runner.py:600` (`def drop_forming(c, tf, t):`)). That rule now has **one** definition, because
§8 needs the same notion of "when did this become knowable" for news, corrections and derived analytics —
not only for candles. `scripts/tests/test_normalized.py` pins the equivalence timeframe by timeframe, so the
unification cannot have changed which bars a live setup may see.

**The timeframe-duration table has four copies** — `build-artifact.py`, `automation.py`, `event-ledger.py`,
`strategy-runner.py`. `available_time()` reads the one `automation.py` owns (it already owns the ladder that
`timeframe-mapping.md` is generated from), and a drift test fails if any copy disagrees. A wrong duration
here would not look like a bug; it would look like a slightly different backtest.

**Quality states are §20's four, not §20's seven.** `AVAILABLE` / `STALE` / `MOCK` / `UNAVAILABLE`, matching
`schemas/data-validation-status.schema.json`. `PARTIAL`, `INVALID` and `UNKNOWN` are `CLAUDE.md` §20's work
and are deliberately not invented early — a state no schema accepts and no consumer understands is worse than
a missing one. `MOCK` outranks freshness: a fixture never reads as live however recent its file.

### 20.1 What we analyse is not what we trade (found via §7 provenance)

Attaching `market_type` to the data made a previously invisible fact explicit, and it is worth stating
plainly: **the crypto candle series is SPOT and the unattended pilot executes PERPETUAL contracts.**

`scripts/fetch-binance-klines.sh:43` calls `api.binance.com/api/v3/klines`, the spot endpoint; the pilot's
venue is `binance_futures`, whose contracts have no expiry and pay funding (`providers.json`
`binance_futures.market_type`). `providers.data_execution_mismatch("crypto")` reports the pair, and a test
fails if it ever stops reporting it.

This is **not** presented as a defect. Spot and perpetual track closely for liquid majors, and analysing one
while trading the other is a common, defensible choice. What was wrong was that it was *silent*. The
consequences it makes explicit:

- Entry, stop and target levels are computed on one instrument's prints and sent to another's order book.
  Basis is small for majors and not zero, and it widens exactly when markets are disorderly.
- The backtest measures a spot-price strategy (`scripts/backtest-methods.py` reads the same series), so
  `CLAUDE.md` §37's "the backtest must execute the same logical system as live" holds for the *rules* and not
  for the *instrument*. That belongs on the §37 row of `SPEC-COMPLIANCE.md`, and is recorded there.
- Funding is a real cost of holding a perpetual and appears nowhere in sizing or in the backtest's fee model
  (`CLAUDE.md` §34's missing fee/slippage inputs, same row).

Closing it is a decision, not a cleanup: either fetch `fapi.binance.com` klines for the traded contract, or
record the basis as a known, measured assumption. Neither is done here — §7's job was to make it visible.

## 21. The point-in-time gate (CLAUDE.md §8, 2026-09-18)

`CLAUDE.md` §8 is one line — `availableTime <= decisionTime` — over **sixteen** kinds of input, from candles
to a provider's later correction of a figure it already published. This repo enforced it for exactly one of
those kinds, in three places, three ways:

| Mechanism | How it decides | Domain |
|---|---|---|
| `scripts/live_rules.py:57` (`def read_at(candles, i, tf, methods):`) | by **index** — may read `candles[:i+1]` and nothing later | backtest/live parity |
| `scripts/strategy-runner.py:600` (`def drop_forming(c, tf, t):`) | by **time** — drop a bar whose period has not elapsed | the live tick |
| `scripts/ict-scan.py:259` (`if i > ref_i: break`) | by **position** — verdicts use the last completed bar `c[-2]`; the forming bar is reported separately and may never confirm a break | the scanner's facts |

Three correct mechanisms answering one question in three vocabularies. Survivable for candles, which all
three were written for. It does not extend: news has no bar index, a provider correction has no position in a
series, and an expectation's creation time is not a candle boundary — so when those arrive there is nothing
for them to reuse, and the likely outcome is a fourth mechanism or none.

**`scripts/pit.py` states the invariant once**, over an input's `available_time`, in a form any of the sixteen
kinds can present. It does **not** replace the three above — each does extra work in its own domain (window
shape, bar dropping, reference selection), and funnelling the live order path through a new abstraction would
be a large change to earn a small one. What it adds:

1. **The sixteen kinds are declared**, and `scripts/tests/test_pit.py` checks that list against §8's own
   bullets. A seventeenth kind in the spec fails the test rather than arriving ungated — which matters most
   for the kinds that have no producer yet, because §28 warns that the moment a calendar joins the backtest
   it leaks by construction.
2. **`event_time` and `available_time` are gated separately.** A CPI figure for a January reference month
   released on 12 February became knowable on 12 February. A test asserts it is refused at a 1 February
   decision time and admitted at 13:30 on the 12th.
3. **Refusals carry the reason and the size of the gap** ("look-ahead of 3600s"), because "wait, it is late"
   and "something upstream is producing future data" need different responses.
4. **Naive timestamps are refused, not assumed UTC.** A naive time in a PIT check is an unanswered question
   about which clock produced it, and assuming is how a DST-shifted local timestamp reads as an hour of free
   look-ahead.
5. **The boundary is `<=`** — a bar closing exactly at the decision instant is readable. `drop_forming()` has
   always drawn the line there; disagreeing by one tick would silently change which bars a live setup sees.

**Where the gate and `drop_forming()` differ, on purpose.** `drop_forming()` inspects only the last row: it
assumes every earlier bar is complete, which is true of the input it gets (a trailing fetch made at the
decision time). Fed a series whose rows run past `now` — which a trailing fetch never returns, but a
corrupted file or a future-stamped row would (`CLAUDE.md` §55) — `drop_forming()` keeps unclosed bars and
`pit.series_as_of()` excludes them wherever they sit. That is the difference between a rule with a
precondition and an invariant without one, and both behaviours are pinned by test so the difference is
recorded rather than discovered.

**Still open for §8:** nothing yet *calls* the gate on the live path, because the kinds that need it —
news, expectations, corrections, revisions — do not exist yet (§17, §24–§29). The candle kinds remain guarded
by the three mechanisms above. This section gives the invariant one definition and one vocabulary; wiring the
new kinds into it is each of those sections' own work, and `SPEC-COMPLIANCE.md` tracks it there.

## 22. Research-integrity bias register (CLAUDE.md §9, 2026-09-18)

`CLAUDE.md` §9 names eleven biases that all historical analysis must protect against. Two were guarded. This
table is the register: one row per bias the spec lists, what guards it here, and — where nothing does — the
section that owns closing it. `scripts/tests/test_research_integrity.py` checks the row set against §9's own
bullets, so a twelfth bias in the spec fails the build rather than going unlisted.

The register exists because "we protect against look-ahead" was true and was being read as "we protect
against bias". Nine of the eleven are open, and several are open in ways that are measurable today.

| Bias (CLAUDE.md §9) | Guard here | State |
|---|---|---|
| look-ahead bias | `scripts/live_rules.py:57` index contract, pinned by `scripts/tests/test_live_rules.py:101` (`class NoLookAhead`) — future-bar mutation *and* truncation; causal FVG cut at `scripts/backtest-methods.py:418` (`def fvg_fill(side, mss, edge, far, stop, H, L, K, n):`); `scripts/pit.py` gate | **Guarded.** Caveat: the one real look-ahead this project had (the ICT FVG rule) was found by a hand-built parity test, not by an automatic check — §38 still has no machine-readable validity verdict on a run. |
| data leakage | `scripts/leakage.py` (mutate the future, compare the decisions); `scripts/research_validity.py` `from_leakage()` (disposition **INVALIDATES**); `scripts/validation.py` `oos()` | **GUARDED since 2026-09-18, in both of its forms.** The look-ahead form is proved by experiment rather than by reading: the prober mutates future bars and fails the run if any decision changes. The disjointness form is `validation.oos()`, which consults the §44 ledger and **never invokes the evaluator on development data**. Caveat that is a finding, not a gap: §44 reports that no period in this repository can validate anything today, so `oos()` currently refuses rather than passes. |
| survivorship bias | — | **NOT GUARDED, and structural.** The instrument universe is a hand-maintained allowlist of *currently listed* symbols (`docs/architecture/instruments.json`), so every backtest runs on survivors by construction — a token delisted mid-window is simply absent from the list and from the history. Nine crypto symbols, all currently trading. Owner: §45. **Unchanged 2026-09-18:** still structural and still the honest answer — closing it needs a delisted-symbol universe that this repository does not have, and §57 forbids building one speculatively. |
| selection bias | `solvent()` (`scripts/rank-setups.py:88`) drops rows with <90 days, blown accounts or negative annualised return *before* ranking | **PARTIAL and measurable.** The floor is real; the selection pressure is unrecorded — **120 candidate rows** across `data/history/stability/*.json` are ranked down to **6 selected setups**, and `docs/architecture/pilot-top20.json` records no candidate count, no rejected rows. Owner: §43. **Accounted since 2026-09-18 (§43):** `research_ledger.budget()` derives candidate, hypothesis and rejected-candidate counts **from the §42 store** rather than from a hand-kept tally, and counts `unrecorded` separately instead of folding it into zero. Counted is not prevented, and the register says counted. |
| data snooping | `scripts/research_ledger.py` `budget()` (parameter searches, dataset reuse, OOS reuse); `docs/architecture/research-ledger.json` | **ACCOUNTED since 2026-09-18, not prevented.** Seven ICT target-model variants were measured over the same data (`docs/backtests/2026-09-11-ict-target-*.md`) plus three deck-faithful switches, with no multiple-testing accounting or disclosure on the reports that picked a winner. Owner: §43. **Accounted since 2026-09-18 (§43):** `budget()` counts parameter searches and dataset reuse, and `research-ledger.json` carries §43's four bias accountings. The seven ICT variants are exactly what those counters are for; they remain undisclosed in the published reports, which is now a measured number rather than an unmeasured one. |
| parameter overfitting | `docs/architecture/analysis-params.json` separates `sourced` (page-cited) from `project_defined` values and requires outputs to label the latter; `MIN_TRADES = 30` (`scripts/stability-report.py:20`); `MIN_WINDOW_DAYS = 90` (`scripts/rank-setups.py:85`) | **PARTIAL.** Sample-size and window floors exist; no parameter-sensitivity sweep, so a value chosen because it happened to win is indistinguishable from a robust one. Owner: §45. **Mechanism exists since 2026-09-18 (§45):** `validation.parameter_sensitivity` is one of the twelve declared methods and `disprove()` returns REFUTED unless every declared check ran — `NOT_RUN` counts against, so an unrun sensitivity sweep cannot read as a pass. No candidate has been through it yet. |
| unrealistic execution assumptions | Taker fee modelled per side (`scripts/backtest-methods.py:44`) | **PARTIAL, three named gaps.** Slippage explicitly not modelled (same line says so). Funding is not modelled at all, though the traded instrument is a perpetual. And the series is SPOT while execution is PERPETUAL (§20.1). Owner: §34, §37. **Flagged since 2026-09-18 (§38):** `EXECUTION_ASSUMPTIONS` is declared per run and `research_validity` gives the condition a **FLAGS** disposition, so every backtest in this repository now carries a FLAGGED verdict that travels with its numbers. The three gaps are unchanged; what changed is that a reader can no longer miss them. |
| future provider corrections | `scripts/feed_health.py` `observe()` → `REVISED` → §20 `INVALID` (live only) | **PARTIAL since 2026-09-18 — live yes, historical no.** A re-fetch overwrites a candle file in place; there is no revision history and no `available_time` on a correction, so a corrected figure silently applies to past decisions. Representable now (`pit.py` kind `provider_corrections`), not yet produced. Owner: §29. **Half guarded since 2026-09-18 (§52):** a closed bar that comes back different is detected LIVE (`feed_health.observe()` → `REVISED` → §20 `INVALID`). A historical re-fetch still overwrites in place with no revision history, so the backtest half is open. Owner: §10. |
| future news revisions | `docs/architecture/event-calendar.json` (`available_time`, `status: revised`); `scripts/event_risk.py`; `scripts/tests/test_event_risk.py` | **GUARDED since 2026-09-18** — the mechanism exists and is tested: a revision published after a decision does not reach it, and a classification change does not leak backwards. What is still absent is an automated news FEED — `providers.json` declares `news` with no provider, so the calendar is hand-maintained and `covers_through` is what makes neglect loud. Owner of the feed: §52. |
| future calendar information | `scripts/event_risk.py` `visible()` / `effective_time()`; `test_event_risk.py::S28_PointInTime` | **GUARDED since 2026-09-18.** An event reaches a decision only when `available_time <= decision_time`, so a row added later — or a classification revised later — does not apply to an earlier decision; and an `actual_release_time` learned after the fact cannot move a window an earlier decision was judged against (§27, §28). Before this, the regex reader scanned the whole calendar file with no availability filter at all. |
| accidental OOS exposure | `scripts/research_ledger.py` `periods()` / `expose()` / `assert_untouched()`; `docs/architecture/research-ledger.json` | **GUARDED since 2026-09-18** — and the guard's first answer is bad news, which is the point. `scripts/research_ledger.py` `periods()` gives every period one of §44's four states with the reason it is in it; `expose()` is **one-way** and records which of the five triggers did it, and `unexpose()` exists only to raise. What it reports today: **no period is untouched**, so nothing here can validate a candidate — which is why §41 cannot approve a proposal. That was always true and was previously invisible. |

### 22.1 "Unknown is a valid state" — guarded, and worth keeping

§9's closing lines are the part this repo already does well, and the register would be misleading without
them. `scripts/htf_context.py` returns `"unknown"` as a first-class value and draws the distinction that
matters: a method returning `unknown` is **silent (no data), not dissenting**
(`scripts/htf_context.py:324` (`A method returning "unknown" is SILENT`)), so it neither blocks nor votes.
The live pilot then refuses to place an order when the higher-timeframe read is `None` — unknown refuses, not
just disagreement (`scripts/strategy-runner.py:1902` (`if st.get("htf") and sig["htf_pass"] is not True:`)),
pinned by `scripts/tests/test_strategy_runner.py` `test_htf_pass_none_must_not_place_an_order`.

That is also §9's "do not force causal explanations where evidence is insufficient" in its enforceable form:
`MIN_TRADES` and `MIN_WINDOW_DAYS` refuse to rank a rule that has too little history to have said anything,
and `solvent()` returns an empty slot rather than a best-available fallback. Tests pin all of it so the
behaviour cannot regress into a confident default.

## 23. Dataset snapshots (CLAUDE.md §10, 2026-09-18)

A research result must identify the data it was computed from. Before this, the top of
`data/history/stability/crypto-live.json` was one key — `generated`, a date — above sixty rows of metrics. No
provider, no symbol list, no timeframe set, no input files, no code version. "Re-run this and see whether it
still holds" had no defined meaning, which is exactly why the 3 %-vs-1 % risk-ceiling drift (§9.y) was
expensive to reason about after the fact: no result said which ceiling produced it.

`scripts/snapshot.py` writes the snapshot; `scripts/stability-report.py` now emits one beside its rows
(additively — `rank-setups.py` reads `rows` and is unaffected). Read the module for the field list. The three
decisions worth recording:

1. **Content hashes, not paths.** §10 asks for a "data version". A path is not one — the fetcher overwrites
   `ohlcv.<SYM>.<TF>.json` in place, so a result citing a path cites a file that has since changed. The
   sha256 of the bytes actually read is the only version this repo can honestly produce.
2. **A dirty tree is recorded as dirty.** `git_sha` alone would claim a reproducibility a modified working
   tree cannot deliver, so the snapshot carries `dirty` and the modified-file count. The test asserts the
   flag is *present*, not that it is false — this tree is usually dirty mid-change, and a test demanding
   cleanliness would simply get disabled.
3. **Provenance is not recomputed.** The snapshot builds on `normalized.load()`, so provider, venue, market
   type and canonical symbol have one implementation rather than two that can drift.

### 23.1 What the snapshot immediately found

Two things, both of which had been invisible because nothing recorded them.

**The source-marker list was half-complete.** `providers.by_source_marker()` was built from a scan of
`data/live/` and `mock/`, which found two markers. `data/history/` — which *every backtest reads* — carried
two more (`binance_public_rest_history`, and a `yahoo_finance_*` family). Snapshots of research data came
back `provider: None` until the snapshot surfaced it. A provider now declares a **list** of markers, with `*`
prefix matching for per-contract families, and a test walks `data/**` asserting every marker present on disk
resolves to a declared provider.

**The CFD backtests run on a different instrument than the CFD system trades.** The commodity history is
**front-month continuous futures from Yahoo Finance** — `XAUUSD←GC=F`, `XAGUSD←SI=F`, `USOIL←CL=F`,
`UKOIL←BZ=F` — while the live feed and the order both go through the broker's **CFD**
(`scripts/fetch-history-cfd.py:6` (`Mapping (futures front-month continuous, NOT the CFD itself)`)).

This was *known and documented* at the fetcher, which lists the four differences and requires them to be
stated "in every report built on this". What was missing is that nothing enforced it: the files are named
`ohlcv.XAUUSD.*` with no hint in the name, the provider was undeclared, and `instruments.json`
`backtested.cfd = ["XAUUSD"]` read as a validation of the traded instrument. Now:

- `yahoo_finance` is a declared provider, `research_only: true` — a third state that is neither staleness nor
  a mock. It is genuinely `connected`; what makes it research-only is that it supplies a **different
  instrument** from the one that gets the order, so a backtest on it is evidence about futures.
- `providers.research_data_mismatch("cfd")` reports `FUTURES` vs `CFD` and returns the provider's own list of
  differences (session hours, contract volume vs tick volume, roll gaps, futures basis to spot).
- `instruments.json` `_cfd_backtested_caveat` says so at the point where the claim is made.

The two mismatch checks are deliberately disjoint: `data_execution_mismatch()` compares what the **live
analysis** reads against what executes (crypto: SPOT vs PERPETUAL, §20.1); `research_data_mismatch()` compares
what the **backtest** reads against what executes (cfd: FUTURES vs CFD). A single function reporting
`{CFD, FUTURES}` against `{CFD}` would say both at once and neither clearly.

Neither is a defect report. Deep history for a related instrument is often the only history there is. What
§10 changes is that a run now records which instrument it measured.

### 23.1.1 Closed 2026-09-18 — and what it left behind

The proxy is gone for the instruments that had an alternative. `ExportHistory.mq5` + `import-mt5-history.py
--write` replaced XAUUSD and XAGUSD **15m, 1H, 4H, 1D and 1W** with the broker's own CFD history: gold back to
**2004** (the futures proxy started 2024) and 15m back to **2018** (it started 2026-07). Both the market and
the sample changed, so every CFD backtest, stability table and ranking made before that date is not
comparable with one made after it — recorded under §59 in `policy.json`, and regenerated the same day.

**What it left behind is the interesting half.** The broker export has no 2H bar and no 30m or 5m for gold, so
`XAUUSD 2H/30m/5m` and `XAGUSD 2H` are still the Yahoo futures proxy. USOIL and UKOIL keep it at every
timeframe, because the MT5 account carries no oil symbol at all.

That leaves **one instrument with two providers across its timeframes** — which is the fault §6 forbids
loudly on the order path, arriving in research where it is far quieter. Every one of those series is
individually valid, correctly labelled and §20 FRESH; a stability table spanning 1H and 2H compares a CFD
against a futures contract and prints one number, and nothing in the old code would have said so.

`backtest-methods.provider_mix()` now records `_source` per (symbol, timeframe) as the series load, and
`assess_run()` turns a mixed instrument into a §38 **FLAGGED** finding naming both providers and which
timeframes came from each. Flagged rather than refused, for the reason §38 exists: refusing would delete the
finding along with the result. The clean answer is to stop ranking CFD setups on the proxy timeframes, which
is what the 2026-09-18 regeneration did — 15m/1H/4H/1D, all MT5.

### 23.2 Configuration snapshots (CLAUDE.md §11)

§11's sixteen fields are the sibling of §10's: the **data** identity and the **configuration** identity are
separate blocks in a run record, linked by `dataset_snapshot_id`. Kept apart deliberately — the same
parameters over different candles, and the same candles under different parameters, are both "a different
experiment", and one merged blob cannot say which changed.

`snapshot.backtest_config_snapshot()` builds the record from `backtest-methods.py`'s **resolved** state;
`stability-report.py --json` now emits it beside the dataset snapshot and the rows.

**Captured by value, which is the entire point.** `bt.RISK` and `bt.MIN_RR` are read at import from
`risk-config.json` and `analysis-params.json` — mutable files. Without the snapshot, a re-run after an edit
measures a different system while the old report keeps claiming the old figures. That is recorded history,
not a hypothesis: the ceiling moved 3 % → 1 % on 2026-09-17 and every report produced before it was silently
modelling a different account (`scripts/backtest-methods.py:72` (`RISK = _te.MAX_RISK_PCT`)). A test mutates
the module after capture and asserts the already-recorded value does not move.

**Every field gets an entry, and a gap is typed.** §11's "include where applicable" is about relevance, not a
licence to omit: a record simply lacking `account_profile` cannot be told apart from one where the account
profile was empty. So `config_snapshot()` refuses a partial record, and absent values are one of two things:

- `unavailable(reason, owner)` — the system cannot capture it yet. Four fields are here today:
  `trading_system_version` (§35, §47), `required_evidence` and `required_analytics` (§35, no dependency
  classification exists), `account_profile` (§33).
- `not_applicable(reason)` — the field is a category error for this kind of run. `methodology_mode` (modes
  gate the `/analyze` Confluence path; a mechanical-rule backtest engages no dimensions), `session` (the
  backtest applies no killzone filter, and `backtest-methods.py:27` says why), and `news_rules` — whose
  reason states the *consequence*, not just the absence: **these results contain no event-risk filtering
  whatsoever**.

**The residual-state trap, found by reading the first output rather than by a test.** `bt.OPTS` is a
module-level dict that `stability-report.py` mutates once per (timeframe, configuration) inside its loop. What
is readable when the loop ends is the **last** configuration's state — so the first version of this record
reported `exit_rules.mgmt: "be"` as though it were the run's setting, when the run had evaluated three
configurations with different management and HTF filters. That is a snapshot lying in the most plausible way
available. Fields derived from `OPTS` now carry `varied_per_config` and point at `setup.configs`, which holds
the matrix that actually applied; a genuinely single-configuration run gets no disclaimer, so the disclaimer
stays accurate rather than decorative.

A second, smaller instance of the same class: `fee_pct_per_side` was emitting `null` on a run whose fee is
declared per configuration, which reads as "we do not know the fee". It now points at
`setup.configs[*].fee`.

## 24. Evidence as a record type (CLAUDE.md §12, 2026-09-18)

The scanner already computes everything §12 calls evidence — `last_mss`, `nearest_fvg`, `unswept_pools`,
`events_recent`, `eq` in `data/live/prelim/<style>.facts.json`. They are flat fields on a symbol: a number or
a string, with no source, event time, availability, quality or methodology scope of their own. The file
header says when the scan *ran*; an individual observation could not say what it was derived from or whether
it was knowable at a given decision time.

The consequence is the reason this is not bookkeeping: **nothing in this system could answer "what evidence
did this decision use?"** A trade file records a `confluence_score` and a `setup_type`; the facts file is
overwritten by the next scan. So a post-trade review (§41) cannot reconstruct the inputs, and §8's gate had
nothing per-observation to gate.

`scripts/evidence.py` adds the missing rung. An `observation()` carries §12's six required fields, deriving
`available_time`, `quality` and `provenance` from §7's normalized layer rather than asserting them, and
refusing outright when it has no way to say when it became knowable — defaulting that to "now" would make
every record trivially admissible, which is worse than refusing.

**Evidence is not a signal, and it is enforced rather than asked for.** §12 says so twice, and the failure it
guards is the easy one: a record that also carries `direction: long` has become a decision, and every
consumer downstream will read it as one. `observation()` refuses `direction`, `side`, `verdict`, `signal`,
`score`, `confluence`, `stance` and `recommendation`, and the refusal names the rung where interpretation
actually lives.

**The six-level ladder is already real here — by file layout.** §13 rule 1 ("numbers from code, words from
the model") is what enforces it. `evidence.LADDER` names each level and the artifact that holds it, checked
against §12's own bullets, so the distinction is inspectable instead of being a convention someone has to
know.

### 24.1 Two things the adapter got wrong first, and what they show

`from_facts()` reads the scanner's existing output — deliberately a reader, not a rewrite: that format feeds
the published pages and `check-model-prose.py`, and changing it belongs with the §35/§36 decision-engine work.

**It guessed the field names.** The first version asked for `last_mss.dir`, `unswept_pools[].side` and
`nearest_fvg.dir` and printed `latest MSS ? past 76862.85`. The real shapes are `.type`, `.kind`/`.level`.
A test now fails on any `?` in a statement, because an unresolved placeholder is the visible symptom of a
schema assumed rather than read. (`pct` is also a fraction, not a percentage — "0.2678%" for 26.8%.)

**It anchored evidence on the forming candle, and the §8 gate refused all of it.** `last_time` in the facts
file is the *forming* bar — reported separately on purpose, since `scripts/ict-scan.py:259` (`if i > ref_i: break`)
keeps it from confirming a break and verdicts use the last completed candle. Anchoring evidence there meant
every record's `available_time` was in the future, and the gate said so. That was the gate being right about
a badly chosen anchor. Evidence now anchors on the completed candle, matching the scanner's own verdict
basis, and a test asserts every record is admissible *at the moment the scan ran* — which is the end-to-end
property worth having.

## 25. Methodology and Setup (CLAUDE.md §13, §14, 2026-09-18)

### 25.1 §13 — verified, not rebuilt

§13 is the section this repo was already closest to satisfying, so the work was pinning it rather than
building it. All three requirements have real enforcement:

- **Multiple methodologies** — `docs/architecture/methods.json` holds four, each with its own skill,
  knowledge sources, chart lane and pane. Nothing hard-codes the set. Agents *may* be shared (structure-agent
  runs both Wyckoff and ICT), which is precisely why the §6.1 de-duplication rule exists.
- **No invented rules** — two mechanisms, and both are code. `scripts/method_purity.py` `violations()`
  refuses a block that borrows another methodology's vocabulary; `scripts/tests/test_doc_citations.py`
  requires every `knowledge/` citation to resolve. The one methodology with no ingested source (Heatmap)
  *says so in its registry entry*, and a test keeps that admission in place.
- **Methodology != Setup != Trading System** — two-thirds real, and now visibly so. A test asserts the
  Trading System layer is still recorded as `NO ARTIFACT` in §17's map, and is written to be updated
  deliberately when §35 lands rather than quietly left passing.

Two of these tests were wrong on the first attempt, in ways worth recording: §13 carries **two** bullet lists
(the methodologies, and what a methodology may *produce* — observations, structure, context, invalidation,
expectations, setup candidates), and reading them as one asked the registry for a dimension called
`observations`. And `method_purity`'s API is `violations(text, method)`, not the `TERMS`/`check` I assumed —
the test now exercises the gate on a real cross-methodology sentence instead of checking that a symbol exists.

### 25.2 §14 — setups are versioned now

§14 asks for four properties: explicit, independently testable, versioned, explainable. Three held. **Versioned
did not**, and the failure was specific: a setup's `id` encodes its parameters
(`crypto-scalping-combined-15m-border-b`) but not a version, `scripts/rank-setups.py` rewrites
`docs/architecture/pilot-top20.json` **in place**, and `trade-file.schema.json` records `strategy` as that id.
So a rule change produces the same id with different behaviour, and every past trade filed under it silently
re-points at rules it was never taken under.

`scripts/setup_version.py` computes a **content** version — a digest of the inputs that decide what the setup
does. A content version and a hand-bumped integer fail in opposite directions: the digest changes exactly when
behaviour changes; a counter is remembered when someone is thinking about versioning and skipped when they are
thinking about the rule.

**What is in:** the setup row's own rule fields (market, timeframe, method, HTF filter, management, execution
venue), its deck-faithful switches, and the global detection parameters it ran with — `min_rr`, the stop
buffer, the displacement and volume thresholds, and the per-timeframe `R/K/T/H/sob` block.

**What is deliberately out, and why:** `RISK`, `START` and `RUIN_FRAC`. Halving risk does not change which
bars qualify, and folding it in would churn every setup's version whenever the ceiling moved — which is how a
version field trains people to ignore it. Risk *is* version-significant for a **Trading System** (§47), which
is a different object and does not exist yet (§35). Passing a risk parameter to `rule_version()` is refused
outright so the boundary cannot be blurred by a later caller. Selection metadata (`rank`, `backtest`,
`negative_backtest`, `symbols`) is also excluded: it describes how a setup *scored*, not what it detects, and
if it moved the version then re-ranking on new data would invalidate every past trade's attribution.

**Wiring.** `finalize()` = carry the deck-faithful switches, **then** stamp versions — in that order, since a
carried switch changes the rules. All three write paths in `rank-setups.py` go through it, and a test asserts
none calls `carry_flags` directly, so a fourth write path cannot ship unversioned setups. The runner stamps
`setup_version` onto the plan; `journal.py` carries it onto the trade file; `trade-file.schema.json` accepts
it as a 12-hex string **or null**, because trades taken before today genuinely have no version and must still
validate.

Regenerating the live selection changed the six selected setups not at all — only the two version fields and
the `generated` date.

## 26. Active trading selection is not an analysis filter (CLAUDE.md §15, 2026-09-18)

§15 is explicit: *"The active trading configuration determines what the user intends to trade. It is NOT a
global analysis filter."* This repo violated it, demonstrably. With the live preset `ict`,
`methods.dispatch_plan("BTCUSDT")` reported `SKIP wyckoff: dimensions.wyckoff is off in /automation` — and
Wyckoff is **live-sourced for crypto**. It was suppressed by a *trading* choice, not by a capability.

One flag was answering two questions. They are now separate:

| Question | Answered by | Output of `dispatch_plan()` |
|---|---|---|
| Which dimensions may qualify a trade? | the method preset (unchanged) | `engaged`, `engaged_count`, `skipped` |
| Which dimensions are still analysed? | `analysis_scope` | `analysed`, `analysis_skipped`, `analysed_not_traded` |

`analysis_scope` defaults to **`available`** — §15's own default, *"the system may continue analyzing all
available methodologies when their data and capabilities are available"*. The old behaviour is still
selectable as `analysis_scope: "preset"` per market, because a user may genuinely not want to pay for reads
they will never trade — but it is now a deliberate narrowing rather than an architectural consequence, and the
skip reason says so.

Two interactions worth stating, both enforced by test:

- **§15 defers to §6.** A dimension is analysed only if it is *live-sourced*. Footprint and Heatmap are not
  analysed under any preset today, because CoinGlass is `mock_only` — analysing them would be the
  mock-satisfies-a-requirement failure of §6 wearing a different hat, and the skip reason names the provider
  and its status.
- **Dispatch is the UNION, not `analysed`.** A dimension the preset *does* trade keeps its agent even when its
  only provider is a fixture; otherwise the deliberate mock rehearsal runs the fixtures exist for would break
  silently. §15 asks for more analysis, not less, so additive is the safe direction.

For the live configuration this changed **no agent dispatch at all** — `structure-agent` serves both Wyckoff
and ICT and was already being dispatched. What changed is that the plan now says Wyckoff is *read but not
tradeable*, instead of pretending it is switched off.

A test that asserted the old behaviour (`structure_agent_is_dropped_when_both_its_dimensions_are_off`) was
updated **deliberately**: its original intent — an agent with nothing to do is not dispatched — still holds,
but only under `analysis_scope: "preset"`, and that is what it now pins.

### 26.1 The display half is NOT done, and why it is a decision rather than a toggle

§15 also requires that *displayed* analysis be independent of trading confluence, and that a user can see
methodology-specific analysis on its own. `scripts/build-artifact.py` still reads the per-market dimension
flags directly, so a page built under preset `ict` shows one lane and one matrix column.

Flipping it is not a one-line change, because the page would gain a **Wyckoff column with nothing in it**.
Since 2026-09-13 the layer-2 local read and the layer-3 full analysis author a block for every ANALYSED
dimension (`scripts/local-eval-brief.py` prints `KHỐI BẮT BUỘC` from `methods.analysed_dimensions`), while
the invalidation owner must be an ENGAGED one (`scripts/check-narrative.py`; since 2026-09-20 the brief prints
that rule too, so a narrower preset cannot leave the stop with a switched-off read). So the lane is drawn with
content under a narrower preset; what it costs is model work on every read tick.

That is a cost and product decision, not a technical one, so it is recorded here rather than taken. Tracked
on the §15 row of `docs/architecture/SPEC-COMPLIANCE.md`.

## 27. Methodology modes (CLAUDE.md §16, 2026-09-18)

§16's two requirements were in opposite states.

**The mode-lock was already right.** "Do not silently change methodology behaviour based on provider
availability" is real code: `methods.mode_of()` is a pure function of the *selected preset*, and a dimension
going unavailable at runtime lowers `engaged_count` without ever changing the mode — so a degraded
multi-dimension preset returns NO TRADE on count rather than quietly becoming SOLO. That was built with the
SOLO decision on 2026-09-12 and is well covered.

**The mode vocabulary had drifted out of both schemas.** SOLO was added to `docs/architecture/methods.json`
on 2026-09-12 and reached neither `trade-file.schema.json` nor `confluence-score.schema.json`, which both
enumerated three modes. The live preset `ict` resolves to **SOLO** — so a conformant `/analyze` record or
trade file *for the current configuration* was schema-invalid for six days, and nothing noticed because
nothing generated the pair. A §59 failure (a registry change not traced to its consumers) wearing a §16 hat.

Fixed in the repo's own idiom rather than by hand-editing two enums: `scripts/sync-methods.py` already
generates two derived spots from the registry and now generates this one too, so `--check` fails the build on
drift and `scripts/tests/test_methods_sync.py` runs it. A test also asserts the specific property that
actually bit — not just that the enums match the registry in the abstract, but that **the mode the current
configuration produces is recordable**.

### 27.1 Two false claims the fix surfaced in the journal

Chasing the mode through its consumers found `scripts/journal.py` filing every pilot trade with two
hard-coded literals, both untrue:

- `"methodology_mode": "NORMAL"` — while the configuration was SOLO. Every pilot trade in the store claims a
  mode the system was not in.
- `"dimensions_used": ["wyckoff", "ict"]` — while an ICT-only setup uses one dimension. Trades were filing
  themselves as having used a methodology that never ran.

Both now derive from the registry (`journal._pilot_mode_and_dims()`): the mode from
`methods.dispatch_plan()`, the dimensions from the rule family's own `requires[]`. Note what this does and
does not claim — `confluence_score: None` already records that no DecisionAgent ran; the mode is the
**configuration the trade was taken under**, which is what `/improve` needs in order to segment outcomes by
mode. An unknown symbol or method yields `None` rather than a guess, and the ingest omits the field instead of
failing, because a journal ingest must not break on an off-allowlist symbol — but it must not invent either.

---

## 28. The analysis scope reaches the page (CLAUDE.md §15 display half, §50, 2026-09-18)

§26 above established the *distinction* (`engaged` vs `analysed`) and left a question open, because the
distinction alone changes nothing a user can see. The three options put to the user were: leave the pages as
they are, show the untraded lane empty, or **author it**. User decision 2026-09-18: **author it** — every
methodology with a live source gets written and displayed.

What made this worth doing rather than cosmetic: the Wyckoff prose **was already being written**.
`data/live/prelim/scalping.BTCUSDT.model.html` contained an `m-wyckoff` block on the day of this change. The
brief did not ask for it, `check-model-prose.py` did not require it, and `build-artifact.py` dropped the
column — so a Sonnet read was produced, validated against nothing, and discarded, every 15 minutes.

### The two roles `engaged_methods()` was playing

The method switch had one accessor serving two questions, which is the same conflation §26 found one level
down. Splitting it is the whole change:

| Role | Reads | Call sites |
|---|---|---|
| **Trading eligibility** — may this lane gate or vote? | `engaged_methods()` | `bias_of`, the ladder, `ict-scan.py`, `backtest-methods.py`, the invalidation owner in `check-narrative.py` |
| **Analysis scope** — may this lane be read and shown? | `analysed_methods()` | `local-eval-brief.py`, `check-model-prose.py`, the read matrix and timeline in `build-artifact.py`, the mandatory context read |

`htf_context.brief_lines()` took the conflation literally: one `methods` argument decided *which anchors keep
their names*, *whether the Wyckoff read is printed*, **and** *what the bias rests on*. It now takes
`reading` alongside `methods`, defaulting to `methods` so every un-plumbed caller is unchanged.

### What deliberately did not move

- **The bias.** `load_tier` is still passed `methods`, never `reading`. §15 widens analysis; §18 keeps
  confluence narrow — *"Only methodologies/evidence explicitly configured by the Trading System contribute to
  trading eligibility."*
- **The ladder.** The timeframe ladder is the decision grid, so it stays engaged-only. The read matrix beside
  it shows every analysed lane. That split is §50's *"Required analysis should be visually distinguishable
  from optional analysis"*, and an optional column says so in words and loses the solid lane underline —
  colour alone would not carry it.
- **The invalidation owner.** A lane that cannot vote must not set the stop.
- **Live-sourcing as the gate.** Footprint and Heatmap are still neither analysed nor demanded: their only
  provider is a fixture, and analysing from one would be the §6 failure wearing a §15 hat.

### A false claim removed

Three states shared one sentence on the page — `Wyckoff: off in /automation`. Two of them were false: the
analysis scope keeps the lane on, so "off" was a claim about the system's own configuration that the
configuration contradicted. They are now three:

| State | Page says |
|---|---|
| analysed, reading written | *analysis only — not traded by the active system, does not count toward confluence* |
| in scope, nothing authored yet | *analysed but no reading written yet — not traded by the active system* |
| genuinely out of scope (`analysis_scope: "preset"`) | *off in /automation* |

Because the brief and the validator must demand the *same* set or a model lands in a fix loop it cannot win,
both read `htf_context.analysed_methods`, which reads `methods.analysed_dimensions` — the one implementation
`dispatch_plan` also uses. `test_analysis_scope_display.py` pins that agreement, and the four guards were
mutation-proved by re-introducing the defect (all four fail).

---

## 29. Expectations as records (CLAUDE.md §17, 2026-09-18)

§17 asked for something the repo had no version of. What it had was `trade-file.schema.json`'s `targets`:

```json
"targets": {"type": "array", "items": {"type": "number"}}
```

Three bare numbers — against a section that opens *"Expectation is broader than targetPrice"* and closes
*"Do not reduce expectations to target prices."* None of the eight fields §17 requires were present
(methodology, source evidence, creation time, availableTime, status, expected path, invalidation condition,
provenance), and the lifecycle vocabulary appeared **nowhere in the repository** — a grep for
POTENTIAL/EXPECTED/CONFIRMED/REACHED/INVALIDATED returned an unrelated trade `status: CANCELLED`, an i18n
label, and some Wyckoff prose.

`scripts/expectation.py` adds the type. Four properties carry the section:

**Immutability is the load-bearing one.** §17: *"Original expectations are immutable… The actual path must
never rewrite the original expectation."* `create()` seals the required fields into `original` as a
`MappingProxyType`; `advance()` returns a **new** record carrying the *same frozen object*, so
`new["original"] is old["original"]` holds — the strongest available statement that the thesis was not
edited. Status lives in a `history` list beside the original, never on top of it. This is what §41's
failure-learning needs: comparing a thesis to its outcome requires the thesis to still say what it said.

**A kind belongs to exactly one methodology.** §17's per-methodology example lists live in
`docs/architecture/methods.json` as `dimensions.<m>.expectation_kinds` — the dimension owns its own
vocabulary. `create()` refuses ICT claiming a Wyckoff kind, which is how *"multiple methodologies must
maintain independent expectations"* becomes enforced rather than intended. `paths_by_methodology()` returns a
**mapping, not a flat list**, because *"do not merge their expected paths"* forbids the merged result — and
the shape a function returns is what its callers will do.

**An expectation is not a signal.** The §12 guard one rung up: `direction`, `side`, `entry`, `position_size`
and `risk_pct` are refused outright. Sizing belongs to the Trading System (§35).

**Three-valued comparison.** `actual_vs_expected()` returns `reached: None` when the actual path is empty,
not `False`. Collapsing "no data" to "failed" would let an empty data window read as a failed thesis, which
§41 would then cluster as a failure pattern.

### Two defects found while building it

- **`json.dumps` cannot serialise a `MappingProxyType`.** A caller writing a trade file would hit a
  `TypeError`, and the obvious workaround — making `original` a plain dict — deletes the immutability the
  module exists for. `to_json()` / `from_json()` own the conversion, and `from_json()` **re-seals**: a record
  loaded from disk is as immutable as a fresh one, or the guarantee would hold only until the first restart.
- **My own `pit.input_` call used the wrong kind** (`expectation`, singular). The §8 registry built earlier
  rejected it against the spec's own enumeration, which is the registry doing its job.

`targets` is kept and relabelled LEGACY rather than deleted: closed trades carry it, and a legacy trade that
silently lost its targets is a worse artifact than an honest legacy shape.

---

## 30. Confluence counts only what the system trades (CLAUDE.md §18, 2026-09-18)

§18 has two halves, and they were in different states.

**The naming half was already right.** The repo says Confluence Score everywhere and never "Confidence %";
`confluence-score.schema.json` declares itself *"a decision-quality measure, not a win-probability
estimate"*; the one `confidence` field is a human pre-trade 1–5 recorded before the outcome is known. Nothing
to fix — verified, not rebuilt.

**The counting half was broken, and §29's predecessor §26/§28 broke it.** `eligible` was defined —
*identically, in the same words, in three places* (`confluence-score.schema.json`, `SYSTEM-DESIGN.md` §6,
`.claude/commands/analyze.md` step 6) — as:

> "data AVAILABLE, not MOCK/STALE/UNAVAILABLE, and actually analyzed"

The preset appears nowhere in that. It was *accidentally* safe only while an untraded lane was also an
unanalysed one. **§15's analysis scope ended that coincidence.** Under the live preset `ict`, Wyckoff is
live-sourced, analysed, and written up every tick — so the old definition marks it `eligible: true`, and an
untraded methodology enters **both the numerator and the denominator** of the ratio that decides trades.
That is §18's own prohibition, twice: *"Confluence must only include explicitly configured methodologies"*
and *"Do not count unrelated methodology analysis."*

Eligibility is now stated as the intersection of two independent questions, neither sufficient alone:

| Clause | Question | Source | Section |
|---|---|---|---|
| (a) | does the active preset **trade** this lane? | `methods.dispatch_plan()['engaged']` | §18 |
| (b) | is its data **live and fresh**? | not MOCK/STALE/UNAVAILABLE | §6, §20 |

`scripts/confluence.py` enforces it rather than describing it — `check()` refuses a record whose eligible set
escapes `engaged`, refuses news/event risk appearing as a scored dimension (§24: a gate, not a lane), refuses
an `engaged_count` that disagrees with what was counted, and refuses an ineligible lane carrying points.
A backtest passes its own historical `engaged` set, so a past run is scored against the configuration it ran
under rather than today's.

All three copies of the old wording were fixed together: leaving one would leave a reader wrong, and the
reader here is a model authoring a decision record.

---

## 31. Contradiction tolerance is configuration (CLAUDE.md §19, 2026-09-18)

Most of §19 was already built, and the audit's job here was to verify rather than rebuild.
`htf_context.bias_of` returns **neutral** when two engaged methods disagree and carries *both* readings into
the basis — `bias.contradiction_two` plus each lane's own reason — which is exactly §19's *"Do not silently
resolve contradictions"* and *"Contradiction must remain explainable in the decision record."* A lane
returning `unknown` is silent, not dissenting, so the other stands alone; only a real reading contradicts.
`confluence-score.schema.json` already carried the anti-cherry-picking rule on `contradictions`.

**The gap was tolerance.** §19: *"The active Trading System determines contradiction tolerance … acceptable
disagreement, blocking behaviour."* The only such rule in the repo lived inside STRICT's own registry note:

> "also requires zero unresolved high-impact contradictions, **enforced in the DecisionAgent procedure, not
> this table**"

Prose addressed to a model, with nothing checking it — and no statement at all for SOLO, NORMAL or ENHANCED.
`modes.<M>.max_unresolved_high_impact` now declares it and `confluence.tolerance()` reads it:

| Mode | Tolerates | Why |
|---|---|---|
| SOLO | 0 | one engaged dimension has no second lane to weigh the disagreement against |
| NORMAL | 1 | two lanes; one unresolved HIGH still leaves a cross-check |
| ENHANCED | 1 | three lanes |
| STRICT | 0 | the spec's own rule, now machine-checked instead of narrated |

**SOLO = 0 tightens the live configuration.** The active preset is `ict` → SOLO, which previously had no
declared tolerance at all; it now blocks at the first unresolved HIGH-impact contradiction. Same reasoning
that raised SOLO's *threshold* to 85 rather than lowering its minimum.

### The asymmetry with §18, on purpose

§18 (previous section) narrowed what may **add** points to the engaged set. §19's anti-cherry-picking rule
keeps collecting contradictions from **every available dimension**, engaged or not. These pull in opposite
directions and both are right: a lane may not add points it is not configured to add, but disagreement it can
see is still information, and dropping it would be the silent resolution §19 forbids. After §15 this is
live — Wyckoff is analysed under preset `ict`, so it can *penalise* without being able to *score*. The
reasoning is written into `scripts/confluence.py` at the place someone would "align" the two, and pinned by
`test_contradiction.py::TheAsymmetryWithScoringIsDeliberate`.

## 32. Six data-quality states, computed (CLAUDE.md §20, 2026-09-18)

§7's normalized layer already produced a quality word per series — `AVAILABLE / STALE / MOCK / UNAVAILABLE` —
and said in its own docstring that "PARTIAL / INVALID / UNKNOWN are §20's work and are not invented early".
`scripts/quality.py` is that work. It does not replace the four-word vocabulary; it answers the finer question
§20 asks, and `from_normalized()` translates between them where a translation exists.

Three of §20's six states were **unrepresentable**, and each absence hid a different error:

| State | What it could not say | The error that hid in it |
|---|---|---|
| `PARTIAL` | "this window has holes" | a gapped series and a complete one produced the same word |
| `INVALID` | "these bars are wrong" | high below low, bars out of order, a repeated timestamp — all read `AVAILABLE` |
| `UNKNOWN` | "I cannot tell" | every uncertainty collapsed into a confident word (§9: *"Unknown is a valid state"*) |

### PARTIAL is computed from continuity, not from a bar count

The obvious test is "did we get as many bars as we asked for", with `automation.SCAN_WINDOW[tf]["bars"]` as
the expected number. Measured against the live files, that test is **wrong**: ASTERUSDT's 1W series holds 50
bars against a 240-bar window and is complete — the coin is a year old. Six instruments would have been
PARTIAL forever, which teaches a reader to ignore the state.

So PARTIAL is computed from **missing bars inside the series' own range** — a fact about the data rather than
about the instrument's age — and only for markets whose tape has no scheduled closures. That is the difference
between a hole and a weekend, and it is now a registry fact: `instruments.json markets.<m>.continuous`, read
through `instruments.is_continuous()`. Measured 2026-09-18 across every live series: all 45 crypto files are
gapless; every XAUUSD/XAGUSD file has gaps (1D: 125) and every one is a session closure. For a non-continuous
market the question is genuinely unanswerable here, so it is left unanswered rather than guessed — §20 forbids
the guess in **both** directions, and reporting weekends as PARTIAL would gate a market on correct data.

`expected_bars` remains available for the caller that really does know its window (a backtest over a fixed
range). The 98% threshold exists because a live feed's most recent bar has legitimately not closed yet.

### The gate, and what it does

§20's second half — *"critical required inputs that do not satisfy their configured quality requirement must
prevent unsafe decision-making"* — existed only as prose a model was asked to narrate. `quality.gate()`
computes it. §20 lists the five outcomes but not the mapping, so this is the project's choice, stated as one:

| State | Outcome | Why |
|---|---|---|
| `STALE` | `WAIT` | the feed works and the bar is late; waiting is exactly the right response |
| `MISSING` | `NO_TRADE` | there is nothing to wait for |
| `PARTIAL` / `INVALID` | `BLOCK_ENTRY` | waiting will not make a holed or corrupt window whole |
| `UNKNOWN` | `HUMAN_CONFIRMATION` | §20 forbids guessing, and a person can look |

Most restrictive wins when several inputs fail, and **only inputs the caller names `required` gate anything** —
§62's rule, expressed as a parameter rather than as a comment.

### The forbidden conversions are refused, not avoided by convention

§20: *"Never silently convert UNKNOWN → LOW, MISSING → EMPTY, STALE → FRESH."* `quality.coerce()` is the one
place in the codebase where such a conversion is spelled, and its entire body is a `raise`. A rule with no code
attached is a rule that erodes; eroding this one now requires deleting an exception on purpose. The legitimate
alternative is named in the error message: a configured allow-list (`gate(allow=…)`), which *says* the system
accepts STALE rather than renaming STALE to FRESH.

### Wired into the one place a decision is made from candles

`strategy-runner.fetch_candles` had a staleness check on the CFD branch and **nothing at all** on the crypto
branch. `_require_quality()` now runs on all three (`strategy-runner.py:369` (`def _require_quality(sym, tf, series, allow=("FRESH",), now=None, at=None):`)), and the asymmetry between live
and replay is deliberate:

* **Live gates.** Candles are REQUIRED_FOR_DECISION for every setup this runner evaluates, so a failing state
  raises — which is how the runner already expresses WAIT / NO DECISION: `tick()`'s fetch loop catches per
  `(symbol, timeframe)`, logs the reason, and leaves that pair with no candles while the others proceed.
* **Research flags.** §38 asks for a run to be "flagged **or** invalidated"; refusing to run would delete the
  finding along with the result. Faults go to a `QUALITY_FLAGS` list and to stderr, once per series rather
  than once per read — a minimal §38 prerequisite, recorded as such.

The research check lives in **`backtest-methods.load()`**, not only in the runner's replay branch. That is not
a detail: `strategy-runner --replay` reaches its data through `bt.scan` → `bt.load`, so a check placed only on
`fetch_candles(at=…)` would have been code that never ran during an actual backtest. The first version of this
was exactly that mistake, and running a real replay with no flags emitted is what surfaced it.

**This found a real defect on the first run.** BTCUSDT, ETHUSDT and SOLUSDT all miss the `2023-03-24T13:00Z`
bar in their 1H history files (two bars on 30m) — one provider outage that every backtest over that range has
silently replayed as whole. The 15m and 5m files are clean, so the fault was invisible to every existing check.
Pinned by `test_quality.py::TheDecisionPathActuallyAsks::test_the_stored_history_really_does_carry_the_fault_this_found`,
which will start failing the day the history is refetched — at which point the fix is to delete the test, not
to widen it.

Every detector is tested by **breaking a real series**: a guard that has never been seen to fail has not been
seen to work. `scripts/tests/test_quality.py`, 52 tests.

## 33. The session model is a registry (CLAUDE.md §21, 2026-09-18)

§21 asks for six properties. Four were already true — the windows exist, the conversion uses real IANA zones,
it is DST-correct per timestamp, and the label is derived deterministically. Two were not, and one of the two
was hiding behind the others.

### Configurable

The same windows were written out in **six** places: the table in `session-model.md` §2, the if/elif chain in
`journal.session_of`, `const SESSIONS` in `chart.js`, `const KZ_WEIGHT` beside it, the `session` enum in
`trade-file.schema.json`, and the weight table in `session-model.md` §3. No generator, no drift test, nothing
that would notice if one moved. "Configurable" is not a property a markdown table has.

`docs/architecture/sessions.json` is now the source; `scripts/sessions.py` is the one reader;
`scripts/sync-sessions.py --write` regenerates the schema enum and both `chart.js` literals; and
`test_sessions.py` runs the sync in `--check` mode so drift fails the build. `session-model.md` keeps what the
JSON does not duplicate — **why** asia is 20:00–00:00 New York, why metals get a full London weight and crypto
never gets one — and says plainly that if its convenience tables disagree with the registry, the registry wins.

**Classes here, points there.** `sessions.json` holds the weight *class* per (asset class, session);
`analysis-params.json timing.weight_by_class` keeps `full` = 7 / `reduced` = 3 / `none` = 0. That split is
deliberate: the class is the model and the points are the tuning surface for `/improve`, and merging them would
mean retuning a number could not be told from changing the model.

### Overlaps

§21 names them as first-class. `journal.session_of` was an if/elif chain, so a window configured to overlap
another would have been resolved by branch order — the silent resolution §19 objects to, applied to sessions.
`active()` returns *every* window an instant is inside; `primary()` collapses to one label by the registry's
declared `precedence`. Today's four windows do not overlap (London 08:00–11:00 local is 13:30–16:00 London
while NY AM runs), so **no label changes** — which is why it is worth installing now rather than after a
window moves. Proved on a throwaway registry with a deliberately overlapping fifth window.

### What the validator caught

`ZoneInfo("EST")` **loads**. tzdata ships the legacy abbreviation aliases, and `EST` is a permanent −05:00 with
no daylight saving — precisely the trap `session-model.md` §1 was written about, since the ICT decks label
their windows "EST" year-round and taking that literally leaves the NY window an hour off the real open for
roughly eight months. A test written expecting `EST` to be rejected failed to raise, and that is how the rule
got written: a zone must be `Region/City` (or `UTC`). That rejects the aliases without rejecting the many real
no-DST zones — `Asia/Tokyo`, `Asia/Singapore`, `Asia/Dubai` — a custom session might legitimately name.

Two further corrections fell out of the same work:

* The trade schema described `session` as *"derived from entry time in UTC"*. It has not been since the
  2026-09-10 decision to use exchange-local clocks; the description was eight days stale and is now generated.
* `chart.js` fell back to `KZ_WEIGHT.crypto` for an unrecognised asset class, shading an unconsidered
  instrument as if it had earned reduced London and NY AM credit. The registry's default is `none` everywhere,
  and the page now agrees with the scorer — pinned by a test that asserts both sides.

### Reproducible

The conversion always was. What was missing is that a session label is stamped on every journalled trade, so
moving a window silently re-labels history: the same trade is `ny_am` under one model and `off` under the next.
`sessions.json` carries `version`, which is what lets a configuration snapshot (§11) say which model produced a
label, and CLAUDE.md §59 treats a session-rule change as potentially Trading System version significant.

**Equivalence.** The new model was run against the old implementation over **70,176 instants across 2024–2025**,
including both DST transitions in both zones: zero differences. A refactor of a labelling rule that cannot show
that is a re-specification wearing a refactor's clothes. `scripts/tests/test_sessions.py`, 34 tests.

## 34. Footprint has a derivation (CLAUDE.md §22, 2026-09-18)

§22 states a chain and a field list, and neither existed:

    Raw Trades -> Trade Classification -> Aggregation -> Footprint
    Preserve: source trades, provider, source venue, market type, timestamp, aggregation rule,
              price level, bid/ask classification, timeframe.

There was no footprint record type at all, so not one of the nine fields was preserved anywhere. The repo's
only footprint was `mock/coinglass/footprint-history.BTCUSDT.json` — and it carried `"delta": +176`, which is
**not JSON**. The file had never been parsed by anything; it is read as text by `flow-agent`. Fixed, with
`test_every_mock_fixture_parses` so the next one cannot sit undetected.

### What is built, and what deliberately is not

`providers.json` declares `trades_raw` and records that **no provider supplies it** — which is exactly why
footprint arrives pre-aggregated — and `methods.live_sourced("footprint", …)` is False for every market.
Building a trades **feed** now, to supply a dimension that is switched off, is the speculative work §0 and §57
forbid. What `scripts/footprint.py` implements is the part that is §22's actual subject and needs no feed:

* `classify()` — step 2, on its own, so it can be tested on its own.
* `aggregate()` — step 3, bucketing to a `tick_size` that is an **argument**, because price granularity is an
  instrument fact: bucketing BTC and XAU to one grid makes one bar a single level and the other ten thousand.
* `build()` — the chain end to end, returning one sealed record per bar with all nine fields required.

When `trades_raw` gains a provider, the wiring is `build(fetch(...), ...)` and the domain logic is already
tested. `test_no_provider_secretly_declares_raw_trades` is the tripwire.

### The classification rule is recorded because it changes the answer

§22 says "Trade Classification" without saying how, because a trade's side is a fact only the venue knows and
everything else is inference. Two rules exist — `VENUE_RULE` (the maker/taker flag) and `TICK_RULE` (infer from
the price change, the classical fallback) — and **they disagree on the same trades**: the test fixture gives
delta `[6.0, -1.0]` under one and `[5.0, 1.0]` under the other. An aggregation whose rule is not recorded
cannot be reproduced (§10, §46), so the rule rides in the record and an unnamed rule is refused.

A trade whose side cannot be determined is `unknown` and **stays** unknown, in its own volume column, out of
the delta. Counting it as a buy would put a fabricated imbalance into every bar containing it — and an
imbalance is the thing this dimension exists to report.

### A vendor bar is not a derived one

§22's last line: *"Never pretend provider-native footprint exists if it does not."* `build()` and
`from_vendor()` are different constructors producing a different `derivation`, and a vendor bar's
`source_trades` is **None, not 0** — it has no trades this system can point at, and a zero would read as "we
looked and there were none" (§9). Its `aggregation_rule` says the vendor does not disclose one, which is the
honest statement of why its levels cannot be reproduced.

`scripts/tests/test_footprint.py`, 31 tests.

## 35. A page must declare its own encoding (CLAUDE.md §50, 2026-09-18)

Found by opening a built page in a real browser at the user's request, after the unit suite was green:
`document.characterSet` came back **`windows-1252`**, and every Vietnamese character in the analysis — which is
the entire substance of the page — rendered as mojibake.

No test could have caught it. The bytes on disk were always correct UTF-8; `test_i18n` compares strings, not
renderings; and the Artifact host wraps the fragment in a head that declares UTF-8, so the *published* page was
always fine. The failure exists only where the file is served or opened directly with no `charset` parameter on
the `Content-Type` — which is precisely how a human reviews a build, and how `--out` is meant to be used.

All three page builders (`build-artifact.py`, `journal_render.py`, `method-panel.py`) now emit
`<meta charset="utf-8">` as the first bytes of the document, inside the browser's 1024-byte encoding pre-scan
window. `test_i18n.EveryPageDeclaresItsEncoding` builds a real page and asserts the meta is in the first 1024
bytes and precedes the `<title>`.

The general lesson is recorded because it will recur: **a rendering property cannot be verified by reading the
source that produces it.** Anything about how a page is displayed — encoding, layout, which lane is shaded,
whether a control responds — has to be checked in a browser.

## 36. A page draws the allowlist, and names what it cannot draw (CLAUDE.md §6, §15, 2026-09-18)

Found during a real-behaviour sweep, in a browser: the CFD page showed **XAUUSD only**. `build-artifact.py`
carried

    GOLD = [_meta("XAUUSD")]
    STYLE_SYMS = {"crypto": CRYPTO, "cfd": GOLD, "forex": [...]}

with a comment explaining that the MT5 EA exports only symbols with an attached chart, so cfd draws gold alone.
**That comment had stopped being true.** A silver chart is attached: `ohlcv.XAGUSD.{5m,15m,1H,4H,1D,1W}.json`
each hold 600 bars from `mt5_bridge_live`, written at the same second as gold's, and
`automation-config.json markets.cfd.instruments` lists `["XAUUSD", "XAGUSD"]`. The page drew one of the two
and said nothing about the other.

The failure mode is the interesting part. §6 requires an unavailable source to be **exposed with its reason** —
but a hardcoded list cannot *become* unavailable, so there was no unavailable state to expose. Available
analysis was suppressed by a literal, which is the §15 error ("the active configuration is not a global
analysis filter") reached from a different direction. No unit test could see it either: every test asserted
against `STYLE_SYMS`, so the list was checked against itself.

Three markets now derive their page symbols from `instruments.analysis(market)` — no hand-written list
anywhere — and `drawable()` splits that allowlist by whether the entry timeframe actually has candles:

| | drawn | named as absent | build |
|---|---|---|---|
| crypto | 9 | — | ok |
| cfd | XAUUSD, XAGUSD | USOIL, UKOIL (no MT5 export) | ok |
| forex | — | all 7 majors | **refuses** |

Naming the absent ones must not turn a page with zero charts into a page, so a market where *nothing* has data
still refuses outright, listing every symbol it wanted — which is where all seven FX majors sit today. The
footer line is a new i18n key, `symbols.absent_named`: *"on the analysis list, no feed attached — not drawn"*.
One of the two CFD cases was a suppressed source and the other an honest absence, and the page previously
could not tell you which, because it mentioned neither.

## 37. Real-behaviour verification (2026-09-18)

At the user's instruction, a green unit suite is no longer the end of a section: the built page is opened in a
real browser and the real CLI paths are executed. Three defects surfaced in the first pass that no test had
caught, and they share a shape — **each was invisible because the test fed the code something other than what
production feeds it.**

| Found | Why no test saw it |
|---|---|
| No `<meta charset>` on any built page; Vietnamese rendered as mojibake | the bytes on disk were always valid UTF-8, and the Artifact host's wrapper supplies a charset, so only a direct open shows it |
| `quality.assess(normalized.load(...))` returned `UNKNOWN` for fresh data → `HUMAN_CONFIRMATION` | the tests fed the **raw** dict, which has `last_updated`; the loader lifts it to `provenance.received_time` — so the documented call path was the untested one |
| The CFD page silently omitted XAGUSD | the tests asserted against `STYLE_SYMS`, i.e. the list checked itself |

The rule that follows: **a property of the running system cannot be verified by reading the source that
produces it.** Encoding, rendering, and anything reached through a different entry point than the test uses,
has to be exercised as the system actually runs it.

## 38. An aggregate cannot be presented as one venue's figure (CLAUDE.md §23, 2026-09-18)

§23 is two sentences and they were in different states — which is why the compliance ledger's `MISSING` verdict
for this section was stale by the time it was re-read.

**Preserving** was already done by the §7 provider work: `providers.json` declares `aggregation_scopes`, and
`coinglass` carries `aggregation_scope: multi_venue` with `underlying_venues: ["UNDECLARED"]` and a note
explaining why naming an unverified venue set would be the same fabrication pointed the other way.
`normalized.provenance()` emits both on every series. One thing was genuinely missing: `mock/coinglass/*.json`
carried **no `_source` marker at all**, so nothing could say which provider had written them — and §23's five
fields could not be attached to a figure even in principle. The marker now exists
(`coinglass_mock`, declared in the provider's `source_markers`) and `aggregated.load()` does the join.

**Presenting** did not exist. §23's rule — *"Never present aggregated information as if it came from one
venue"*, with its own worked example of "Aggregated OI across venues" becoming "OKX OI" — lived as prose inside
a registry note, which is the shape a rule takes just before it stops being applied. `aggregated.attribute()`
is that rule with code attached: asking for a single-venue label on a `multi_venue` record raises, quoting §23
and the example. `describe()` produces the honest phrasing instead.

### Why `attribute()` takes a venue at all, rather than not existing

Because the legitimate case is real: a `single_venue` provider's open interest genuinely **is** Binance's, and
saying so is not a violation. A guard that made attribution impossible would be routed around within a week.
`attribute()` permits exactly the case the registry says is true, refuses the one §23 names, and *also* refuses
naming the wrong single venue — which the prose rule never covered.

### The scopes were declared and read by nothing

`aggregation_scopes` had been in the registry since §7 and no code had ever looked at it, so a provider could
have carried a scope no one had defined and §23 would have had nothing to test against. `providers.py` now
exposes `AGGREGATION_SCOPES` and validates at import that every provider's scope is in the vocabulary, and that
a `multi_venue` provider names *something* — `["UNDECLARED"]` being the honest value where the vendor has not
disclosed, and `[]` reading as "checked, none", which is a different and false claim.

`scripts/tests/test_aggregated.py`, 16 tests, including §23's own example verbatim against the live registry.

## 39. Four event shapes, one reader (CLAUDE.md §12, 2026-09-18)

Found by the full suite going red on **live data that had changed under it** during a publish tick — not by a
new test. `scripts/ict-scan.py` emits four event shapes: a LEVEL event (`sweep`, `erl_*`, `mss_*`), a ZONE
event (`fvg_*`, carrying `lo`/`hi` and no `level` at all), a MULTIPLE event (`volume`), and whatever a later
rule adds. `evidence.from_facts` read `ev.get("level", "?")` for all of them and called every one *"swept"*.

So an FVG became `recent: swept fvg_bull ?` — a placeholder where a number belongs, and a verb wrong twice
over: an FVG is formed, not swept, and a volume spike is neither. It had sat there since the adapter was
written, invisible because the live scan happened to have no FVG in its recent window; it appeared the moment
one did.

Each shape now reports what it actually carries, and **an unrecognised shape is skipped** rather than printed
with a `?`. A record that says nothing is honest; one that says `?` is a fabricated observation that §12 would
carry into a decision. The five shapes are now constructed in tests rather than waited for.

## 40. Event Risk, rebuilt (CLAUDE.md §24–§32, 2026-09-18)

Nine sections, one subsystem, and the most safety-critical thing found in this pass. What existed was
`strategy-runner.event_blackout`: a regex for `YYYY-MM-DD HH:MM` run over the **entire text** of
`event-calendar.md`, blocking within ±30 minutes of any match, returning `None` on every failure. Three
defects, all live on the code path that places orders:

1. **The calendar's own documentation was a live blackout.** The "How to add an entry" example on that page
   matched the regex, so a prose line restricted real trading. The parser could not tell prose from data.
2. **A three-hour window had a two-hour hole in it.** A row written `17:00Z – 20:00Z` parsed as two POINT
   events at 17:00 and 20:00, each ±30 minutes — leaving **17:30–19:30 unprotected** inside an FOMC window.
   That is §30's "Do not create accidental gaps", demonstrated.
3. **Every failure read as "no news".** Missing file, unreadable file, empty table — all returned `None`,
   which the caller takes as permission. §32's single explicit prohibition, on the order path.

None was fixable by improving the regex, because the input was never a data format.
`docs/architecture/event-calendar.json` is; `scripts/event_risk.py` is its one reader; the markdown page is
now the explanation and points at both.

### What each section contributes

| § | Requirement | How it is met |
|---|---|---|
| 24 | Event Risk is a gate, not a methodology; 10 min before / after, **configurable** | `policy.pre_minutes`/`post_minutes`, overridable per event; `confluence.NOT_A_DIMENSION` already refuses it as a scored lane |
| 25 | HIGH / MEDIUM / LOW / UNKNOWN; UNKNOWN never silently LOW | `policy.by_impact`; UNKNOWN does not restrict by default but STRICT turns it into NO TRADE, which LOW never does |
| 26 | Relevance is per instrument | event `currencies`/`countries`/`asset_classes` matched against the instrument's canonical id and asset class |
| 27 | scheduled vs actual release time | two fields, and an actual time is used only once it was *available* |
| 28 | `availableTime <= decisionTime` for news | `visible()`; a later revision does not reach an earlier decision |
| 29 | Calendar snapshot | `snapshot.id`/`version`/`covers_through` |
| 30 | Deterministic windows, union of overlaps, no gaps | `windows()` merges, including **adjacent** windows |
| 31 | Existing positions are separate | `policy.existing_positions.action`, default HOLD |
| 32 | Fail-safe on missing/stale/invalid | `CalendarUnavailable` carrying the configured action, default BLOCK_ENTRY |

### Three decisions worth stating

**The vocabulary drift was real.** `SYSTEM-DESIGN.md` §6.3 and `analyze.md` both said **MODERATE** where
CLAUDE.md §25 says **MEDIUM** — a third word for a level the spec names, which meant no code could ever have
matched the documented enum. Found by a test asserting the spec's own word; both corrected.

**Event risk moved from once-per-tick to per-instrument.** It used to be computed once at the top of `tick()`
and applied to all nine symbols. Under §26 that is wrong in both directions: an EIA petroleum release would
either block Bitcoin or, if narrowed, stop protecting oil. It is now asked per symbol at the point of use,
and `event_blackout()` called **without** a symbol fails closed rather than answering a question that has no
global answer.

**A stale calendar is loud.** `covers_through` is the date past which the file makes no claim. Past it, every
instrument reads UNAVAILABLE and the fail-safe applies. That is deliberate: the failure mode of a
hand-maintained calendar is not corruption, it is neglect, and neglect that produces silence is
indistinguishable from an all-clear.

**The asymmetry between entry and open positions is deliberate.** A missing calendar blocks new entries (§32)
and does **nothing** to open positions (§31) — it does not start closing them. Closing is itself a trading
decision with cost and slippage; §31 says not to make it automatically, and the two risks are not symmetric.

`scripts/tests/test_event_risk.py`, 62 tests, one class per section, each of the three original defects
written as a named regression test.

## 41. The Account Profile (CLAUDE.md §33, 2026-09-18)

`CLAUDE.md` §33 names fifteen account attributes and says **"Account rules must be configurable."** One of
them was configuration (`max_risk_pct`, `risk-config.json`). Four more were literals inside the live order
engine:

```python
MAX_OPEN = {"futures": len(CRYPTO), "mt5": len(CFD)}
MAX_TRADES_PER_DAY = 3
EQUITY_HALT_FRAC = 0.85
CONSEC_LOSS_HALT = 5
LEVERAGE = 3
```

Those are not runner settings. They are the account's rules — a 15 % drawdown limit, a per-symbol daily entry
cap, a position cap, a failure condition, a leverage limit — and keeping them in `strategy-runner.py` made two
things impossible. A second account could not have different ones (§5: *"do not assume that all CFD accounts
have identical rules"*), and no research run could record which rule set produced a result (§11: a backtest
run under a 15 % drawdown limit is not the same experiment as one run under 5 %).

**One registry, one reader.** `docs/architecture/account-profiles.json` holds a profile per account;
`scripts/account_profile.py` is the only module that reads it. Two accounts exist, both DEMO: the Binance
USDT-M testnet the crypto pilot trades, and the MT5 demo the CFD/FX setups trade.

### Four rules that make it a domain object rather than a config file

**A declared `null` is not a missing key.** Every profile must spell out all sixteen rule keys; `null` means
*this account has no such rule* and an absent key is refused at import. "Nobody wrote a daily-loss limit down"
and "this account has no daily-loss limit" are different facts, and a reader that cannot tell them apart will
eventually enforce a limit nobody wrote or skip one somebody did. It is §20's three-valued discipline applied
to account state.

**A profile may only tighten.** `max_risk_per_trade` above the platform ceiling is refused at import, naming
the ceiling's one authored source. A `news_restrictions` block that would *shorten* a calendar buffer, or drop
an impact level the calendar restricts, is refused at call time. An account is a constraint on what a Trading
System may do; it is not a licence to do more, and an account that could lower the platform's event-risk floor
would be an account that opts out of §24 by writing a config key.

**Objectives are not gates.** `profit_target` and `min_trading_days` are reported by `objectives()` and appear
in neither gate. Reaching a profit target must never block an entry — that is the one way a "limit" list can
silently invert the meaning of success.

**An unevaluable rule is never permission, and never a halt.** A declared rule whose input is missing reports
`UNKNOWN`. On the entry path `UNKNOWN` blocks. On the account path it does **not** write the kill switch,
because "I could not read the balance" is not "the account is down 15 %". The two gates are separate functions
for exactly this reason: `entry_gate()` for new entries, `halt_check()` for account survival.

### What changed on the order path

| Was | Is |
|---|---|
| `len(open_same) >= MAX_OPEN[venue]` | `AP.entry_gate(profile(venue), …)` — position cap, daily cap, and (for an account that declares them) session / overnight / weekend / news rules |
| `equity <= EQUITY_HALT_FRAC * equity_start` | `AP.halt_check(profile(v), …)` — max total drawdown, daily loss, trailing drawdown, consistency, declared failure conditions |
| `consec_losses >= CONSEC_LOSS_HALT` | the same call, re-run after this tick's closes are booked |
| `LEVERAGE` | `futures_leverage()`, from the crypto account's `max_leverage` |
| `ER.blocked(sym, at=…)` | the same, on a calendar the account may have tightened |

Every value is unchanged except one: the MT5 account's position cap. It was `len(CFD)` = 4 while **cfd and
forex both route to the mt5 venue**, so the cap that bounds that account's book did not count the seven FX
majors — flagged in `SPEC-COMPLIANCE.md` §4 as belonging with the §33 work. It is now derived across every
market routed to the venue (11). Binding effect today is nil: forex is `default_enabled: false`, no FX setup
exists, and one-position-per-symbol already dominates. Raising a live cap is a decision, not a refactor
side-effect, which is why it waited for this section rather than being tidied up in passing (§59).

### Real money has no profile, on purpose

There is deliberately no profile for `environment: "real"`. `for_venue()` raises when asked for an account it
has no rules for, so switching `execution.environment` to `real` cannot place an order until somebody has
written that account's rules down — a third lock beside the runner's own refusal and the MT5 EA's demo-account
check (§51). The resolution failure is *kept* rather than raised at import, so `--report` still tells you what
the account is holding; an undeclared account stops orders, not observation.

### No prop profile ships; the prop rules are tested

`PROP_CHALLENGE` and `PROP_FUNDED` exist in the vocabulary (§5's five context types live here, not in the
market model). No such account exists, so no such profile ships — §57. But a §33 that only stores rules for
accounts with no rules would be indistinguishable from no §33 at all, so `scripts/tests/test_account_profile.py`
builds a complete prop-challenge profile in-test and drives every limit through the *same* validator and the
*same* evaluators the live profiles use: daily loss on day-start equity, trailing drawdown from peak,
consistency on the best day's share of profit, session / overnight / weekend restrictions, a three-loss failure
condition, and a profit target that reports progress without gating.

`scripts/tests/test_account_profile.py`, 63 tests, including five that drive a full dry `tick()` with a
fabricated signal and read the refusal out of the runner's own `signal` log — because a unit test of the
evaluator proves the rule computes, not that the order path consults it.

## 42. The risk model charges what the trade costs (CLAUDE.md §34, 2026-09-18)

`CLAUDE.md` §34 lists eleven inputs a risk calculation must consider. The live path considered six. The two
missing ones were missing in opposite ways, and one of them was a live defect rather than an omission.

### The defect: a gross floor against net evidence

The runner's R:R gate compared `r_planned` — `|target − entry| / |entry − stop|`, a **gross** number — against
the 3R floor. That floor was **measured net of fees**: `analysis-params.json`'s own basis line records
"Measured on the last year of ICT 15m setups … (fee 0.05 %/side)", and `backtest-methods.py:517` subtracts
`2 * fee_pct / dist` from every R before counting it.

So the live gate was strictly looser than the evidence that justified it, by a margin that grows as the stop
tightens — round-turn cost in R is `2 · fee / (|entry − stop| / entry)`:

| stop distance | cost at 0.02 %/side (maker) | at 0.05 %/side (taker) |
|---|---|---|
| 1.0 % | 0.04R | 0.10R |
| 0.5 % | 0.08R | 0.20R |
| 0.2 % | 0.20R | 0.50R |

A setup planning exactly 3.00R gross on a 1 % stop is 2.96R net. It was being taken as though it cleared a
floor it did not clear. Two existing test fixtures had to move because of this, which is the clearest evidence
the change bites: `test_strategy_runner.HtfGateFailsClosed.ONE_SIG` planned exactly 3.00R, and
`test_min_rr_and_risk.LiveGate` asserted that 3.0 passes. Both now assert the opposite, with the reason
written at the assertion.

**The order type is not a guess either.** `sig["entry_now"]` means a MARKET order at the bar close (taker);
everything else rests a post-only GTX limit (maker). Charging one rate for both would over-price the ICT
family and under-price the Wyckoff one.

### Slippage is UNKNOWN, not zero

`risk-config.json costs.slippage_pct` is `null` deliberately. Every figure `risk_model.py` returns carries
`slippage: "UNKNOWN"` and `net_is_upper_bound: true`, so no caller can read "we did not model it" as "it is
zero". It is the one finding in `validate()` marked `blocking: False` — blocking on a cost that cannot be
measured until the pilot has recorded fill-vs-intent data (§41) would not be a risk control, it would be a
permanent refusal to operate. Filling the number in later is a config edit; a test pins that.

### Existing exposure is summed, not counted

The pre-existing cap counted positions. Two positions with a 2 % stop and twenty with a 0.1 % stop are the
same exposure and a count cannot tell them apart. `open_risk()` sums `qty × |entry − stop|` and returns it as
a fraction of equity; a position whose risk cannot be computed is returned in `unknown` and never as zero,
because an unmeasurable position is the one most likely to be the large one.

### No more magic fallback on the order path

`min_notional()` swallowed every exception and returned a literal **50.0** — a number no venue published,
used to decide whether a real order was large enough to send. Both failure directions were silent: too high
and a valid order is skipped, too low and the venue rejects it after the runner has booked the attempt. It
now raises `RiskRefused` and the call sites log a skip with the reason.

### Live and research must price the same trade the same way

`pilot-top20.json` records the `fee_assumed` of the ranking run that selected each setup, and those values were
not even internally consistent — two crypto setups on the same venue carried 0.0002 and 0.0005. The fee is a
property of (venue, order type), so it is declared once in `risk-config.json costs` and a test asserts every
selected setup's assumption is one of the venue's declared rates. A setup validated at a fee the account does
not pay is evidence about a different trade.

`scripts/risk_model.py` is the one reader; `scripts/tests/test_risk_model.py`, 37 tests.

## 43. The Trading System, and the four words §62 is about (CLAUDE.md §35, 2026-09-18)

`CLAUDE.md` §35 asks for a Trading System artifact and then makes one demand of it that no other section
makes twice: *for each analysis/evidence/analytics dependency, classify it as `REQUIRED_FOR_DECISION`,
`OPTIONAL_FOR_ANALYSIS`, `VISUALIZATION_ONLY` or `RESEARCH_ONLY`. This classification is mandatory.*

Before 2026-09-18 those four names appeared in `CLAUDE.md`, in three code comments and in one Vietnamese
prompt string — and **nowhere in code or config**. The dependency model was binary: a dimension was engaged
or it was skipped (`scripts/methods.py:432` (`engaged.append(d)`)). §36's ordering, §40's hot-path rule and
§62's invariant are all statements *about* the classification, so none of them had anything to assert on;
`scripts/snapshot.py` was typing `required_evidence` and `required_analytics` as `unavailable(…, "§35")` for
exactly that reason.

### The style is the Trading System

`(market × horizon)` already names everything: it is `automation.STYLE`, it is what a page is built for, it is
what a `pilot-top20.json` row's `market` + `horizon` fields say, and it is what `/analyze` is run against. So
`docs/architecture/trading-systems.json` declares **one system per style — nine — and does not declare the
style set**: the reader refuses to load unless its keys equal `automation.STYLE.values()` exactly. A style
with no Trading System would be a scan and a page with nothing declaring what may gate them; a Trading System
with no style would govern nothing.

Almost nothing else is declared there either. Market, timeframe, instruments, market types, sessions,
methodology presets, setups, entry and exit rules, the risk ceiling, custom constraints and event-risk buffers
are all **resolved** by `trading_system.describe()` from the registries that own them. §35 asks a system to
declare its composition, not to become a tenth copy of nine other files. Two fields are genuinely declared,
because neither can be derived: `version` (§47) and `account_profile` — `cfd-scalping`, `cfd-day` and the
three `fx-*` styles have no pilot setup row today, so there is no execution venue to derive an account from,
and naming one anyway is what makes the account's rules apply the day one of them is switched on rather than
the day after.

### Three rules, in code

1. **Required-ness cannot be inherited.** Each dependency declares a `baseline_role` — the role it has in a
   system that did *not* name it — and the loader refuses a registry where any baseline is
   `REQUIRED_FOR_DECISION`. A dependency therefore gates only a system that wrote its id down, and the
   gating set of all nine systems is one reviewable list (`dependency_profiles.pilot-v1`, fifteen ids).
2. **Unknown context resolves REQUIRED, never optional.** Some roles are conditional — the higher-timeframe
   read is a gate for a setup that declares `htf: true` and is not consulted at all by one that does not.
   The condition is a named predicate (`setup.htf`, `setup.method_requires`, `preset.engages`) and when it
   cannot be evaluated for lack of a setup row or an engaged-dimension set, the answer is
   `REQUIRED_FOR_DECISION`. "I was not told which setup" must never read as "not required".
3. **Only `REQUIRED_FOR_DECISION` may gate.** `trading_system.assert_may_gate()` raises `NotGating` on the
   other three roles, and every dependency-derived block in the live order path now goes through it
   (`scripts/strategy-runner.py:1827` (`def blocked_on(dep, why, _st=st, _style=ts_style, _sym=sym):`)) —
   account rules, the event-risk blackout, venue reconciliation, the higher-timeframe bias and the net R:R
   floor. §62 says a required analysis must never silently become optional; this enforces the inverse too,
   which is the half that loses trades rather than the half that loses money: an optional, visualization or
   research input can never quietly become a gate.

There is no runtime setter. `reclassify()` exists only to raise and say that a role change is a registry edit
plus a §47 version bump, so that a latency optimisation cannot reach for it.

### The homonym this forced into the open

`methods.json` already warned that the runner's `WYCKOFF-BOOK`/`ICT` methods are mechanical rule families and the
Confluence dimensions of the same name are the skills' discretionary reads. The classification makes the two
behave differently and visibly so: `analytics.wyckoff_rules` is required exactly when the *setup's method*
names `wyckoff` in `runner_methods[*].requires`, while `methodology.wyckoff` is required exactly when the
*active preset engages* the dimension (§15). On `cfd-swing` today that produces a system which requires
`analytics.wyckoff_rules` (its setup runs the WYCKOFF rules) and does **not** require `methodology.wyckoff`
(the cfd preset trades ICT only) — which is precisely what the published page has been saying in words:
"Wyckoff: analysis only — not traded by the active system, does not count toward confluence."

### Two things it found

* **Three of six pilot setups had no governing system on the first wiring.** The scanner half of the repo
  spells timeframes `1h`/`4h` (`automation.STYLE`, `SCAN_WINDOW`) and the backtest/pilot half spells them
  `1H`/`4H` (`backtest-methods.py` `P`, and therefore every `tf` field in `pilot-top20.json`). `for_setup()`
  resolves by the row's declared `horizon`, which has one spelling; `for_market_tf()` folds case and says why.
* **The backtest engine does not apply three of the dependencies its system declares required** — the event
  calendar, the account's entry gates, and venue reconciliation (it has no venue). The configuration snapshot
  now records that as `required_evidence.declared_but_not_applied_by_this_engine` rather than smoothing it
  over. §38 names "incomplete required inputs" as grounds to flag a research run, and it cannot flag what no
  record mentions.

`scripts/trading_system.py` is the one reader; `scripts/tests/test_trading_system.py`, 46 tests.

## 44. The decision ordering is now a walk that can refuse itself (CLAUDE.md §36, 2026-09-18)

`CLAUDE.md` §36 opens with *"The Decision Engine must preserve canonical decision ordering"* and lists
seventeen steps. This repo had **two** orderings and neither was that one: twelve prose steps in
`.claude/commands/analyze.md`, and whatever sequence `tick()` happened to execute. Nothing compared them,
and nothing could, because the canonical list existed only as prose in the spec.

`docs/architecture/decision-order.json` is now that list — §36's seventeen steps, in its numbering and its
own wording, with a drift test that parses §36 out of `CLAUDE.md` and fails if the two disagree. Each step
declares three things beyond its name: which `trading-systems.json` dependencies it consults (§35), whether
it `may_block`, and where it lives **on each of the two paths** — or `null` plus a reason. That last field is
the one that did the work: a step no path implements now has to say so.

### The Trace

`scripts/decision_order.py` turns the list into something a decision walks. A `Trace` records each step as it
happens and refuses three things outright:

1. **Out of order.** Recording step 14 and then step 10 raises. Steps may be skipped — forward only.
2. **Blocking where blocking is forbidden.** Step 17 is the only step with `may_block: false`. A refusal
   discovered while generating an execution instruction is a defect in steps 1–16, not a decision.
3. **Blocking on something that may not gate.** A blocking record naming a dependency goes through §35's
   `assert_may_gate`, so an `OPTIONAL_FOR_ANALYSIS` / `VISUALIZATION_ONLY` / `RESEARCH_ONLY` input cannot
   stop an entry by being consulted at the wrong step. Step 11 (expectation) is the live example: it exists,
   it may block in principle, and `display.expected_path` is VISUALIZATION_ONLY, so a Trace that tries to
   block there raises.

`verify()` adds the completeness question — an order was generated only if nothing before it blocked — and
the walk is written into every `signal` log line as `decision_trace`, which makes the ordering auditable
after the fact rather than only assertable before it.

**Computing early and consulting in order is not reordering.** Several values are computed once per tick
(candle quality, the account's survival state, venue reconciliation, the event-risk precheck) and consulted
at their canonical position per signal. What reordering would mean — and what the Trace catches — is an
early result being allowed to skip a later gate.

### Two real defects, found by writing the order down

**Step 3 did not exist.** §36 asks for an Event Risk *Precheck* — "an early safety and data-availability
check" — and keeps it separate from step 14's per-instrument window check. The live path had only step 14.
So "the calendar cannot be read at all" (§32's fail-safe case) was discovered once per signal, deep inside
the order loop, instead of once per tick before any work was done on a decision that could not legally be
made. `tick()` now runs `ER.load(at=t)` as its own step, logs `event_precheck` with the configured action,
and blocks new entries for that tick — while steps 1 and 2 keep managing what is already open, because §31
says news restrictions apply to new entries and open positions are governed separately.

**Step 12 ran at step 17.** The two calculations that can refuse to size an order — `min_notional()` on
futures, the `volume_min` floor on MT5 — lived inside `place_limit()`/`place_market()`. A signal that could
not be sized was therefore declared **eligible** at step 16 and then quietly did nothing at 17.
`scripts/strategy-runner.py:1133` (`def risk_precheck(sym, st, sig, equity, risk_mult):`) runs those two
refusals at step 12, before eligibility. It computes no order payload — rounding, the venue call and the
final guard stay in `place_*()`, which remains the authority and still runs its own check on the *rounded*
quantity. The precheck moves the refusal, not the arithmetic.

### And a third defect, found by running it rather than testing it

The §36 wiring was verified by driving a **real** dry tick — real candles, real event risk, real account
profile, real sizing — and three of the nine execution symbols blocked at step 12 with *"SOLUSDT's exchange
filters carry no MIN_NOTIONAL entry"*. The venue had published one. `min_notional()` parsed a span of TEXT
(`'MIN_NOTIONAL'.*?'notional': '…'`), which silently requires the venue to print `filterType` before
`notional`; Binance prints `{'filterType': 'MIN_NOTIONAL', 'notional': '50'}` for BTCUSDT and
`{'notional': '5', 'filterType': 'MIN_NOTIONAL'}` for SOLUSDT. So SOL, RENDER and ONDO could not be sized at
all. It now parses the filter **object** and reads `notional` from within it, order-independently.

Every test in `test_risk_model.py` had stubbed the connector with the one key order that happened to work —
which is why this survived §34's 37 tests and died on the first real tick. Two regression tests now drive
both orders. Under the pre-§34 code the same symbols would have silently used the literal `50.0` guess; the
refusal was correct behaviour on incorrect input, which is the least visible kind of defect.

### What is still absent, and says so

Three of the seventeen are declared unimplemented on the live path, each with its reason in the registry:
**step 4 (session)** — no session gate exists on any path; the sessions registry scores, it does not gate;
**step 8 (required methodology analysis)** and **step 15 (contradiction / confluence)** — the pilot runner
trades mechanical rule families, not the discretionary Confluence dimensions, so neither a skill read nor a
Confluence Score reaches `tick()`. That is the §37 "same logical system as live" caveat in its sharpest
form, and it is recorded rather than papered over.

`scripts/decision_order.py` is the one reader; `scripts/tests/test_decision_order.py`, 33 tests — including
a parse of the runner's own source that fails if a trace call appears out of §36 order, or if a step the
registry calls implemented is never recorded.

## 45. The backtest is proved point-in-time by attacking it (CLAUDE.md §37, 2026-09-18)

§37 makes two demands. Neither had been *established* — one was argued from a comment, the other was not
measurable at all.

### 1. "Only information available at the historical decision time may affect the entry decision"

A code review cannot establish this. An experiment can, and `scripts/leakage.py` is that experiment:

1. Run the engine over a real series and record every decision.
2. Replace every bar **strictly after a cut** with something wildly different — same length, same
   timestamps, same field names, different prices.
3. Run it again.

Every decision whose entry happened at or before the cut must come back **byte-identical**. Only the outcome
fields may move, which is exactly what §37 permits: *future market movement may determine stop hit, target
hit, MFE, MAE, trade outcome.* Three mutation modes run — `scale` (×3 away from the cut's close), `freeze`
(a flat line at it) and `invert` (mirrored through it) — because a single mutation can agree with the
original by accident.

**Mutation, not truncation.** Cutting the series short would change `len(candles)`, and with it the pivot
windows and every loop bound of the form `n - 3` — so a difference in the output would mean nothing.
Replacing bars in place leaves the engine's shape untouched and varies only the information the future
carries.

**The probe is itself mutation-tested.** A probe that cannot fail proves nothing, so
`scripts/tests/test_backtesting.py` feeds it three deliberately leaky engines — one whose entry price is the
best price in the whole series, one whose trade *exists* only because a later bar exceeded a level, and one
honest control — and requires the first two to be caught.

**Result:** all five runnable rule families pass on real BTCUSDT 15m history with non-zero coverage
(WYCKOFF 27 decisions checked, COMBINED 26, ICT 4, WYCKOFF-BOOK 2, COMBINED-BOOK 2). The one helper that
could plausibly leak — a 3-bar pivot is only confirmed at `i+3` — is causal by construction and now has a
test that walks the boundary rather than trusting the docstring.

### 2. "The same logical Trading System and Decision Engine semantics used by live decisions"

Since §36 this is measurable. `docs/architecture/decision-order.json` now carries a **third column**: per
canonical step, where it lives on the backtest path or why it is absent. Twelve of the seventeen are
implemented; five are declared absent (event-risk precheck, session, required methodology, final event
validation, contradiction/confluence), each with its reason, and a test checks that list against what the
§11 configuration snapshot *independently* reports as not applied — two hand-written statements kept to one.

### The divergence that writing the column found

The live R:R gate has measured R **net of fees** since §42 (§34's work): a signal whose gross R clears 3.0
but whose fee cost in R takes it below is refused. `simulate()` was still filtering on the **gross**
`R_planned` and charging the fee afterwards. So the backtest was taking trades the live runner declines —
measured at **392 of 8,071 admitted trades (5 %)** across BTC/ETH/SOL 15m. A backtest that admits 5 % of
trades its own live system would refuse is not measuring that system.

`simulate()` now computes the fee first and applies the floor to net R, which is the same gate
`rr_reason()` applies live. The asymmetry is worth naming: the error direction was *optimistic* — every
affected trade was one the live system would never have taken, so every historical result was computed on a
slightly more permissive system than the one that trades.

**This is a research-semantics change (§59).** Every `data/history/stability/*.json` report and every
`backtest` block inside `docs/architecture/pilot-top20.json` was produced under the gross convention and is
**not comparable** to a run made after 2026-09-18. They are deliberately **not** regenerated here:
re-ranking the pilot's setups is a decision about what the pilot trades, not a documentation fix, and it
belongs to a `rank-setups.py` run the user asks for. Until then the numbers in those files are honest about
a system that is no longer exactly the one running.

`scripts/leakage.py` is the prober; `scripts/tests/test_backtesting.py`, 19 tests.

## 46. A research run now has a verdict (CLAUDE.md §38, 2026-09-18)

§38 is two sentences. The repo could already **detect** most of the first one's ten conditions and did
nothing with any of them.

* §20 computed data-quality faults and printed them to stderr.
* §37's prober found look-ahead and reported to a test.
* §11's configuration snapshot recorded which REQUIRED dependencies the engine never consults — written for
  §38's benefit and read by nobody.
* The engine's unmodelled costs lived in a Vietnamese caveat paragraph under the tables.

Four detectors, four dead ends. Underneath each of them the performance table printed exactly as it would
have for a clean run — which is the second sentence's failure verbatim: *never silently produce a
trustworthy-looking performance result from invalid research.* Detection without a verdict is how that
happens.

### The registry decides what a defect means, once

`docs/architecture/research-validity.json` holds §38's ten bullets in §38's own order and wording (a test
parses them back out of `CLAUDE.md`, so an eleventh cannot be added to the spec and skipped here). Each
carries the disposition §38 offers — **FLAGS** or **INVALIDATES** — and the reason for it. Choosing per call
site is how everything ends up flagged.

**The line between the two is the direction of the error.**

* **INVALIDATES** — the numbers are about trades that could not have been taken as measured, and the error
  runs in an unbounded, usually flattering direction: `look_ahead`, `leakage`, `invalid_timestamps`,
  `future_calendar_state`, `future_methodology_state`, `oos_contamination`.
* **FLAGS** — the run measured something real, but not the thing it claims: a narrower dataset
  (`unavailable_historical_data`), a bad bar (`corrupted_provider_data`), a cheaper venue
  (`unrealistic_execution_assumptions`), a less-constrained system (`incomplete_required_inputs`).

The last one deserves its test written out, because it is the one that could become a loophole. The three
dependencies this engine omits — `event_risk.calendar`, `account.profile_rules`, `venue.reconciliation` —
are all **gates**: omitting a gate can only *add* trades, so the run measures a superset of the live system
rather than a flattered version of it. Omitting a dependency **invalidates** the moment it could change a
trade's *terms* rather than only its existence — an omitted sizing input, stop rule or price source. That
sentence is in the registry, next to the disposition it justifies.

### Four properties, each closing a way this rots

1. **Escalation only.** `finding()` accepts a *stronger* disposition than the registry's (corruption across
   the whole series, not one bar) and **raises** on a weaker one. The direction that loses information is
   shut.
2. **Not-checked is a state.** An assessment that looked at nothing returns `UNVERIFIED`, not `VALID`. A
   blank assessment looks exactly like a clean one, which is the thing §38's last sentence is about.
   `UNVERIFIED` is not one of §38's two words and says so in the registry.
3. **Unstamped is refused, not trusted.** `read()` raises on a research artifact carrying no verdict.
4. **No setter.** A verdict is a function of the findings; there is no override path.

### What it found

Running it is what turns three standing prose caveats into verdicts on real files:

* **Every backtest of this engine is `FLAGGED`**, on two counts — six unmodelled execution facts
  (`slippage`, `spread`, `funding`, `min_notional`, `lot_step_rounding`, `partial_fills`) and the three
  declared-but-unapplied required dependencies. Both were already true and already written down; neither had
  ever reached a reader of the numbers.
* **`--combined-entry hindsight` invalidates the run that used it.** That switch picks between two fill
  prices using a *later* bar — look-ahead by construction, kept for comparison against the causal rules —
  and until now a report produced with it was typographically indistinguishable from one produced without.
* **The Caveats section is now generated from `EXECUTION_ASSUMPTIONS`**, because the hand-written list had
  already drifted: it named slippage and funding, not MIN_NOTIONAL or lot step.
* **Three conditions are honestly unverified on every run** — `leakage` (the residual a future-mutating
  probe structurally cannot see: a parameter fitted over the whole history, a survivor-only symbol set),
  `future_methodology_state` (§47 owns it), `oos_contamination` (§44 owns it). They appear by name in every
  stamp rather than being absent from it.

### Where the verdict travels

Above the tables, not in a footnote — §38's second sentence is a claim about what a reader meets first.

| Artifact | Carries |
|---|---|
| `backtest-methods.py` markdown | the verdict block **above** the first performance table |
| `backtest-methods.py --json` | `research_validity` + a §11 `config_snapshot` (it had neither) |
| `stability-report.py --json` | `research_validity` beside `dataset_snapshot` and `config_snapshot` |
| `rank-setups.py` report + `pilot-top20.json` | the verdict of **every source file**, and what was refused |

`rank-setups.py` is where it bites, because its output is not a report — it is what the runner places orders
from. All three ranking modes read their rows through one `load_rows()`, so that is where the gate sits: a
source whose verdict is `INVALID` is **dropped**, and the refusal is recorded in the written artifacts.

**`UNSTAMPED` is the one deliberate softening, and it is not silent.** Every existing
`data/history/stability/*.json` predates the verdict. Dropping them would empty the pilot's entire input on
the day the stamp was introduced — a live-behaviour change dressed as a documentation fix (§59). Instead
each row carries `UNSTAMPED`, stderr says so per file, the report line says so, and the selection file
records it; `--require-stamped` makes the strict behaviour available now and should become the default once
every stability file has been regenerated. `UNSTAMPED` ranks **above** `FLAGGED` when reporting the worst
source: a flagged run was assessed and its defects are named, an unstamped one is entirely unknown.

`scripts/research_validity.py` is the one reader; `scripts/tests/test_research_validity.py`, 52 tests.

## 47. Twenty-three metrics, one computer, and no score (CLAUDE.md §39, 2026-09-18)

§39 is a list of twenty-three metrics plus two rules. The list was two-thirds built; the two rules are where
the failures were.

### What the audit found

Sixteen of the twenty-three existed, computed in **two independent places** — `journal.stats()` and
`stability-report.metrics()` — that agreed by accident, with **zero tests over any of them**. Seven were
absent (average drawdown, MFE, MAE, Sharpe, Sortino, Recovery Factor, time in drawdown, and the three
probabilities). Four more were wrong in the same way: `journal.stats()` folded every `R <= 0` into `losses`,
so a **flat trade sat in the win-rate denominator and extended the losing streak** — which is precisely the
trade that management produces when it moves a stop to entry.

### The registry and the one computer

`docs/architecture/performance-metrics.json` holds §39's twenty-three in §39's own order and wording (a test
parses them back out of `CLAUDE.md`). Each declares its `kind`, what it `needs`, its definition — and a
**`min_n`**, the sample size below which it is not computed at all.

`scripts/performance.py` is the only thing that computes them. Four properties:

1. **Sample size is not optional.** `n` is written by the constructor, and a metric below its floor returns a
   reason instead of a number. Three trades do not have a Sharpe ratio; eight might.
2. **Unavailable is a value, never `None` and never infinity.** Profit factor with no loser, Sortino with no
   downside, P&L with no account — each returns `{"unavailable": reason}`. A placeholder sorts, and sorting
   is how a placeholder becomes a decision.
3. **Breakeven is the third bucket**, because §39 lists it beside wins and losses. It stays in the win-rate
   denominator (it happened) and breaks **both** streaks (it is neither).
4. **A probability carries its method.** `risk_of_ruin: 0.07` on its own is a decoration. Each of the three
   comes back with its method (bootstrap over the observed per-trade R distribution), iteration count, seed,
   horizon, risk fraction and sample size — the §46 reproducibility set.

### Why bootstrap rather than the closed form

The classic gambler's-ruin formula assumes a two-valued bet. A system with a 3R target and a 1R stop does not
have one, so the closed form would answer a question about a different strategy. Resampling the **observed**
R distribution assumes nothing about its shape.

Writing it found a real defect in the first version: it stopped each simulated path at the account's failure
threshold, which made `risk_of_ruin` **structurally zero** for every account whose drawdown rule is tighter
than the ruin level — i.e. every account. The three events are now tracked by *when* they first happen. Ruin
stays absorbing; a failure is not, because §33's conditions describe a rule being breached, and the equity
curve continues whether or not a rule says to stop. `account_failure_probability >= risk_of_ruin` now holds
by construction rather than by luck, and is tested.

### MFE and MAE, measured where the bars are

The one §39 gap that needed new data. `backtest-methods.py` `walk()` is the only loop that sees the bars
*between* entry and exit, so it now records the best and worst unrealised R of every trade. §37 explicitly
permits future bars to determine an outcome, and `leakage.py` already listed `mfe`/`mae` in `OUTCOME_FIELDS`,
so the PIT prober does not read them as look-ahead. The metric reports winners and losers separately, because
"the losers that first went to +1.8R" and "the winners that first went to −0.9R" are the two questions MFE
and MAE exist to answer.

### The rule that is about what you must NOT build

> "Do not optimize against a single universal metric."

There is no `score()` in `performance.py`. There is `refuse_universal_score()`, whose body raises and whose
message says what to do instead: rank **lexicographically** over named metrics in a declared order, the way
`rank-setups.py` already does (not blown up → positive quarters → positive years → worst quarter →
stability), so a reader can see which criterion decided. A weighted composite hides that, and §48 requires
the objective to be exposed.

### Where it is wired

`backtest-methods.summarize()` (the five report columns keep their names, units and meaning; the twenty-three
arrive additively under `perf`), `stability-report.metrics()` (the keys `rank-setups.py` reads positionally
are untouched), and `journal.stats()`. The journal's legacy `wins`/`losses`/`win_rate`/`worst_losing_streak`
keep the old two-way convention **on purpose** and say so in the docstring: a figure quoted in an earlier
review must keep meaning what it meant (§59). `perf.*` carries the three-way split beside it.

`scripts/performance.py` is the computer; `scripts/tests/test_performance.py`, 54 tests, with the arithmetic
checked against hand-computed values rather than against the implementation's own output.

## 48. The live path is measured, and the research path is off it (CLAUDE.md §40, 2026-09-18)

§40 has two halves. The repo failed each in a different way, and the second failure had been missed by two
previous audits.

### Half one: measurement

§40 names ten timestamps and four statistics. What existed were **four wall-clock stamps at one-second
resolution, none of them ever differenced** — so the gap was not capture, it was measurement — plus no
`perf_counter` anywhere in the order path's whole import closure and no latency test in any of the 53 test
files. Nothing could have told you a stage got slower.

`docs/architecture/latency-model.json` declares §40's ten stamps in §40's own wording; `scripts/latency.py`
is the only recorder and the only summariser. Four decisions, each closing a way a latency number lies:

1. **`perf_counter_ns`, not wall clock.** Wall clock is not monotonic and one-second resolution cannot see a
   hot path at all.
2. **Spans close in `finally`.** `tick()` has five early returns; a timer that stops only on the happy path
   reports the fast cases and drops the slow ones. Where a `with` could not wrap a region without
   re-indenting the live order path — the per-signal decision walk — `record()` is called at **both** exits,
   the blocked signal that `continue`s and the eligible one that reaches execution.
3. **Transport-bound stages are recorded but summarised apart.** This repo polls REST and reads MT5 files, so
   `market_event → provider_receive` and `order_submission → fill` are dominated by the poll interval and by
   how patient a limit order is. One table containing both cannot tell a reader which it is looking at. Only
   two of the ten are exempt this way, and the registry refuses an exemption that does not say why.
4. **Sample size travels** (§39's rule): a p99 over seven observations is not a p99. A stage with no
   observations is **absent**, not zero.

**Nearest-rank percentiles, not interpolated** — with a poll loop's sample sizes, interpolation invents a
value between two observations and reports it as one. Writing the test found the first version using
`round()`, whose banker's rounding returned the 96th observation for p95 over 100.

Recording is best effort throughout: §1 puts execution safety above measurement, so a recorder that cannot
write degrades to silence and never to a refused trade. The first real dry tick immediately paid for itself —
it found a missing `import time`, and then showed a **1.8-hour** `market_event` lag on 4H data, which is the
poll lag §40 wants visible rather than assumed away.

### Half two: isolation

> "Research, learning, backtesting, AI reasoning and post-trade analysis must NOT block the live decision and
> execution path."

The LLM half was true and provable: the live path imports nothing that calls a model, and a repo-wide grep
for `anthropic`/`openai` under `scripts/` (excluding tests, which mention the words to check this) is empty.

The post-trade half was **false**. `pilot-loop.sh` ran `journal.py all` — an index rebuild plus an HTML
render, of unmeasured duration — **synchronously between the tick and the sleep**. It is model-free, but §40
is not about models, and "usually fast" is not isolation. It is now detached the same way `scan-loop.sh`
detaches every model read (`( nohup … & )`, stdin closed), behind an atomic `mkdir` lock so two runs cannot
race on `trades/index.jsonl`, with a stale lock older than an hour cleared so a killed run cannot silently
stop every later ingest.

The registry's `workloads` table is what makes the isolation claim checkable: every workload §40 names is
declared as hot or research, and every research entry says **how** it is kept off the live path.

### The regression tests §40 asks for

§40 lists eight stages that performance regression tests should cover. `test_latency.py` benchmarks each,
offline on fixtures — a regression test that reaches the network measures the network — and a final test
asserts that every stage in §40's own list has a benchmark, so a ninth cannot be added to the spec and
skipped here. They are **not budgets**: §40 sets no threshold and neither do they. Each ceiling is generous
and exists to fail when a stage becomes orders of magnitude slower — an accidental network call, an O(n²)
rewrite, a model in the hot path.

`scripts/latency.py` is the recorder; `scripts/tests/test_latency.py`, 40 tests.

## 49. Eight outcome states, and the decision only a human may make (CLAUDE.md §41, 2026-09-18)

§41 makes three demands. Each had been missed in a different way.

### Five of the eight states were unrepresentable

A trade file carries WIN / LOSS / BREAKEVEN. The other five — NO TRADE, BLOCKED ENTRY, MISSED OPPORTUNITY,
EXECUTION FAILURE, DATA FAILURE — had **nowhere to live**. The runner wrote every block reason, every venue
rejection and every quality refusal into `top20-log.jsonl`, and **nothing ever read it back**. "The filter
saved us" and "the filter cost us a winner" were the same silence.

The gap was never capture. `scripts/outcomes.py` `ingest()` turns lines the live path already writes into
records something can count: a blocked signal becomes BLOCKED_ENTRY **naming the dependency that blocked it**,
a venue floor refusal becomes EXECUTION_FAILURE while an ordinary skip stays NO_TRADE, a quality error becomes
DATA_FAILURE. Running it on the real pilot log produced 36 evaluation states that had been invisible.

`distribution()` reports **every** declared state including the zeros, because "no execution failure was
recorded" and "execution failure cannot be recorded" look identical in a dict that omits empty keys — and the
second was this repo's actual state.

### "NO TRADE and BLOCKED ENTRY must NOT automatically be classified as failures"

The operative word is *automatically*. `is_failure` is **three-valued**: `True`, `False`, or `None` for "this
needs a counterfactual nobody has computed". Evaluation states default to `None`, and the registry **loader
refuses** an evaluation state that declares anything else — the guard is in the code, not in a convention,
because this is §41's most easily reversed rule.

LOSS is `None` too. A loss inside the system's own expectancy is the cost of the edge; what makes a loss a
*failure* is a cause, and that is a separate field. Marking every loss a failure is how a working system gets
improved out of existence.

`resolve()` computes the counterfactual where the plan and the later bars exist: a blocked entry that would
have reached target becomes MISSED_OPPORTUNITY, one that would have stopped out reveals `beneficial_filtering`,
and one that did neither says so. **The horizon travels with the verdict** — "would have won" is meaningless
without "by when", and a long enough horizon makes almost anything a missed opportunity.

**UNKNOWN is a real cause and the default.** §41: "Do not force every outcome into a causal category." A
distribution in which every outcome has a confident cause is a distribution nobody checked.

### "AI must NEVER silently rewrite the production Trading System"

The operative word is *silently*, so the mechanism is that a change must be a visible, recorded,
human-decided artifact. `Proposal` is that artifact, and three things enforce it:

1. **`decide()` refuses any actor but `human`** — including a rejection, because a model that can reject can
   also bury a finding.
2. **Approval is refused while a stage is unwalked**, and a stage cannot be marked complete without evidence
   (a path, a report, a run id) — a stage marked done with nothing behind it is the pipeline being skipped
   politely.
3. **`outcomes.py` has no writer at all.** No `json.dump`, no write mode, no rename. It reads the repo and
   returns records. A learning module with a writer is one refactor away from applying its own conclusions.

**Nothing in this repo can be approved today, and that is the design working.** §41 puts OOS Validation
(§44) and Robustness/Sensitivity (§45) *before* the human decision, and neither is implemented. `decide()`
raises `PipelineIncomplete` naming them. A human may still REJECT or DEFER through the gap — the block is on
adoption, and rejecting a candidate needs no OOS run.

`scripts/outcomes.py` is the reader; `scripts/tests/test_outcomes.py`, 51 tests, each of the three rules given
its own attempt to subvert it.

## 50. An experiment is a sealed record, and a decision is its successor (CLAUDE.md §42, 2026-09-18)

§42 asks for a ten-stage lifecycle, twenty-two recorded fields per experiment, and one sentence with teeth:
*"Experiment records must be immutable."*

**Nothing in this repo recorded an experiment at all.** Backtests were run by hand, their parameters lived in
a shell history, and the only trace that a candidate had ever been evaluated was a markdown file somebody
remembered to write. §43 (experiment budget) and §44 (OOS exposure) are both *impossible* on top of that,
because both need to count what was tried — which is why §42 comes before them.

### Completeness is checked at seal time

`Record.seal()` refuses while any of §42's twenty-two fields is neither set nor explicitly
`unavailable(reason)`. A record missing `random_seed` is not "mostly filed"; it is a result nobody can
reproduce (§46), and it should be impossible to file. A test removes **each** of the twenty-two in turn and
requires the seal to fail — the fields are individually load-bearing, not a checklist that passes on average.

`unavailable()` must say why. A field left absent and a field that could not be captured are different facts,
and only one of them is a defect — but a missing key cannot tell them apart.

`code_version()` records the commit **and whether the tree was dirty**, because a dirty tree means the commit
does not identify the code that ran, and §46 makes that the difference between a reproducible result and a
plausible one.

### Immutable three ways

A convention catches none of these, so there are three mechanisms:

1. The sealed record is a `MappingProxyType` — mutation raises.
2. `write()` refuses a path that exists, and opens with mode `"x"` so the filesystem enforces it too.
3. The record carries a `content_sha256` over exactly the twenty-two fields, and `load()` re-checks it.

The third is the one that matters: an edit through an editor, a script or a merge **never goes through this
module**. The point is not that nobody would edit a record — it is that an edited one must be *detectable*.
`all_records()` skips a tampered file rather than returning it, so a corrupted record cannot quietly join a
count that §43 will later present as an experiment budget.

### A decision is a successor record, not an edit

`decide()` seals a **new** record naming its predecessor and that predecessor's hash. The experiment as run
and the judgement passed on it are two facts with two timestamps; editing the first to carry the second
destroys the only evidence of what was known when the evidence was complete. The original keeps
`decision: PENDING` forever, and that is correct.

`PENDING` is not one of §42's own words. §42 lists `decision` as a field and §41 names the three outcomes;
`PENDING` is the honest value of that field *before* a human has decided, and it exists so a record can be
sealed the moment its evidence is complete rather than waiting days for a decision. The registry says so
rather than leaving a reader to wonder why there is a fourth value.

`decide()` refuses any actor but a human, for the same reason §41 does.

### The two lifecycles are pinned to each other

§41's pipeline (11 stages, trading outcomes → human decision) is the *learning loop*; §42's lifecycle (10
stages, observation → approval/rejection) is the *record of one trip around it*. They are different lists in
the spec, so both are declared — and every §42 stage carries `stage_of_41`, checked against the real §41
registry, so the two cannot drift into describing different processes.

`scripts/experiment.py` is the reader and writer; `docs/experiments/` is the store;
`scripts/tests/test_experiment.py`, 28 tests.

## 51. The research ledger: what was tried, and what trying it cost (CLAUDE.md §43 + §44, 2026-09-18)

Two sections over **one** structure — the experiment history. §43 counts what was tried; §44 asks what those
tries did to the validation data. Splitting them into two registries would duplicate the period model and the
copy would drift the first time a period changed state, which is exactly the failure §44 is about. One
registry, `docs/architecture/research-ledger.json`, two sections.

Both were impossible before §42 gave the repo an experiment store, because both need to count what was tried.

### §43: "Do not hide the number of experiments performed"

Every one of the seven counters is **derived** from the §42 store. A counter maintained by hand beside the
store is a counter that will eventually disagree with it.

Two distinctions the counters are built around:

* **A hypothesis is not a candidate.** Two experiments testing the same hypothesis on different data are one
  hypothesis and two candidates — and the candidate count is the multiple-testing denominator.
* **A sweep is not a candidate.** An experiment whose parameter diff names a range, a list or a `sweep` is
  counted under `parameter_searches`, because a sweep of twenty values is twenty tests wearing one hypothesis.

**Unrecorded is not zero.** A counter that is zero because nothing was recorded reads exactly like one that is
zero because nothing was tried. Two real searches predate the store:

| what | bias |
|---|---|
| 7 ICT target-model variants (range / std2 / std25 / std4 / erl_next / irl, plus the pivot/highest origin switch) over one dataset | data snooping |
| 120 candidate rows narrowed to 6 selected setups, with nothing recorded about the 114 | candidate selection bias |

They are reported in `unrecorded` and **deliberately not folded into the counts** — an unrecorded search that
has been added to a total is indistinguishable from a recorded one.

Rejected candidates are counted, because a rejected candidate still consumed a test. §43's denominator is
everything that was tried, not everything that survived.

### §44: exposure is a one-way door

Four states, five triggers, and one rule: *"Do not label it as pristine validation anymore."*

`expose()` moves a period to `oos_exposed` and records which of the five triggers did it. `unexpose()` exists
**only to raise** — present so the refusal is something a caller can find and read, rather than an absence
they work around by editing the registry, which is the move it exists to make awkward. The error names the
only thing that actually restores validation capacity: carving out a new period nobody has read.

Exposing twice is idempotent; exposing `development` data raises, because that data was never validation and
a caller who expected otherwise believed something false about which data it was using.

The loader refuses a period labelled `oos_untouched` whose own stated reason says it was read — the
contradiction §44 exists to prevent, caught by the loader rather than by a reader's attention.

### The honest current state

**No period in this repo can validate anything.** Both declared periods — the 2023–2026 crypto history and
the ten-week 2026 CFD window — are `development` data: every stability report and every ranking run read the
whole span, and the 2026-09-13 solvency rule was written *after* looking at what the CFD window contained,
which is data snooping and is recorded as such.

This is stated in the registry and pinned by a test, rather than implied by an empty list. A genuine OOS
period has to be **carved out and left alone** before it can validate anything, and doing that is a decision
about what the pilot trades (§59), not a documentation change.

It is also why §41 cannot approve anything: `Proposal.decide()` refuses because OOS Validation is a stage this
repo cannot perform, and this is the file that says why.

`scripts/research_ledger.py` is the reader; `scripts/tests/test_research_ledger.py`, 32 tests.

## 52. Validation is a disproof, and silence is not a pass (CLAUDE.md §45, 2026-09-18)

§45's list of twelve methods is the easy half. The operative sentence is:

> "Actively attempt to disprove candidates. Do not only search for evidence that a candidate works."

That is a claim about the **default**, and a validation suite's default lives in exactly one place: what it
does with a check that did not run. If `NOT_RUN` counts as a pass, a candidate survives by being untested —
the shape every validation suite fails in.

So `disprove()` returns `REFUTED` unless every declared check ran and none broke the candidate, and
**`NOT_RUN` counts against it**. A candidate with no checks at all comes back `NOT_RUN`, never `SURVIVED`. The
registry loader even refuses a `NOT_RUN` description that has been softened into a pass, because that is the
one edit that would quietly invert the whole module.

### Methods take an evaluator, not a dataset

Each method is given a callable mapping a configuration to a trade population. That is what makes the suite
testable: a validation suite that can only be exercised by running three hours of backtests is a validation
suite nobody runs. Every method is tested against a deliberately **fragile** synthetic system — a result that
only exists at one parameter value, an edge carried by one symbol, a fill that must be exact — because a
validator that has only ever seen a robust candidate proves nothing.

Four of §45's twelve methods (regime, instrument, session, time-period variation) share one `partition()`
implementation. §45 lists them separately because they are four *questions*; the arithmetic is one, and four
copies would drift.

### No thresholds live in the registry

§45 says what to check, not where to draw a line. A line drawn in the registry would be a project parameter
masquerading as a rule, so every check takes its threshold as an argument and **records it in the result** —
a reader can see what "survived" was measured against, and disagree with it. A test asserts no numeric value
appears in any method or check entry.

### Three checks that report rather than pass

- **survivorship** — structural (§9): the instrument set holds only currently-listed symbols, so every
  population is survivors by construction. No threshold makes this pass; it is a property of the set.
- **selection bias** and **multiple testing** — both refuse while §43's denominator is incomplete. Two
  searches predate the experiment store, so a correction computed from the recorded part would *understate*
  the real multiplicity. Reporting `NOT_RUN` with the reason is the honest answer; a number would not be.

### OOS refuses before it measures

`oos()` asks §44's ledger first and **does not invoke the evaluator at all** on development data — the test
asserts the evaluator was never called. Measuring the data a candidate was built on and labelling the result
validation is the precise failure §44 exists to prevent, and it must not be reachable by accident.

### What this unblocked, and what it did not

§41's `Proposal.decide()` used to refuse approval because OOS validation and robustness were *unimplemented*.
Both now exist. The registry was updated to say so — and the refusal **still stands**, for the right reason:
`blocked_by()` now consults the §44 ledger live, and no period in this repo is untouched, so there is nothing
to validate on. Hardcoding the old refusal would have left a stale block standing on the day a period is
finally carved out; a test proves approval works the moment one is.

`scripts/validation.py` is the runner; `scripts/tests/test_validation.py`, 39 tests.

## 53. Reproducible, and a different system (CLAUDE.md §46 + §47, 2026-09-18)

One question asked twice. §46 asks it of a **result**; §47 asks it of the **thing that produced one**. The
Trading System version is an item in both lists, which is why they share a registry: `version` must not be
able to mean two things.

### §46's teeth are in its last sentence, and it is about comparison

> "A result without reproducibility metadata must not be treated as equivalent to a fully reproducible
> experiment."

The harm never happens in the record. It happens when a partial result and a complete one appear as two rows
of the same table, where a reader treats them as equivalent whatever the footnote says. So:

* `assert_comparable(a, b)` **raises** when the grades differ, and names what the weaker result is missing.
* `compare()` returns both grades **inside** the result rather than beside it — a caller who wants to render
  only the numbers has to delete them on purpose.

Grading names what is missing rather than counting it: "7 of 9 captured" tells a reader nothing about whether
they can re-run something, and the two that are absent are the entire answer.

**Three ways a capture list gets ticked off without capturing anything** — a `None`, an empty container, and
an `unavailable()` marker — are each rejected by `_present()` and each has a test. An all-`unavailable` §42
record must not grade as reproducible, and does not.

**`provider_state()` is the one item nothing else captured.** A dataset snapshot records what was *asked
for*; a configuration snapshot records how; neither records *who answered, in which role, with what declared
capability*. A result computed while a provider was degraded is a different result and nothing else in the
capture list would show it.

**A null seed is now a gap, not an exemption.** It was defensible while nothing in the repo was stochastic —
the previous audit said so. §39's bootstrap and §45's Monte Carlo ended that.

### §47's teeth are in "rejected candidates must remain traceable"

A version counter hands `v1.3` to a new candidate the moment the old `v1.3` is rejected and forgotten.
`next_candidate()` reads the **§42 experiment store** instead, so a number that has been worn stays worn —
including by candidates that were rejected, which is exactly the traceability §47 asks for. A test files a
rejected candidate and requires the next number to skip it.

**There is no third version form.** A released system is `v1`, `v2`, `v3`; a candidate is `v<parent>.<n>` so
its parent is readable from its own name — §47's own example is `v1 → v1.x → v2`. `parse()` rejects `v1.0`,
`v1.2.3`, `v2-experimental` and `candidate-7`, because §47 forbids a separate incompatible version system and
a grammar that accepts `v2-experimental` is how one starts.

**All thirteen listed change kinds are significant, and none can be declared otherwise.** §47 calls them
"examples", which is a floor and not a ceiling, so `is_significant()` accepts an explicit override *upward*
(`also_significant=True` for an unlisted change) and offers none downward. A test asserts the signature has no
parameter that could turn a listed kind off — that is the direction in which a version silently stops tracking
the system.

`scripts/versioning.py` is the reader; `scripts/tests/test_versioning.py`, 37 tests.

## 54. One rule, two sections: no universal score, no assumed answer (CLAUDE.md §48 + §49, 2026-09-18)

> §48: "Do not create a universal 'best system' score."
> §49: "Do not assume the filter improves performance."

The same rule pointed at different things. Both forbid a conclusion from being baked into the machinery that
is supposed to reach it. §48's version is a weighted blend whose weights *are* the objective while looking
like arithmetic; §49's is an A/B that can only come out one way because the arms were not actually identical.

### §48: seven objectives, all lexicographic

Every objective is an ordered list of named keys with a direction each — never a blend. `rank()` reports the
**deciding key per row**, so "why is this first" has an answer that is not "the score". The registry loader
rejects an objective carrying a `weight`, which is the single edit that would turn the whole thing back into
a universal score.

Different objectives give different winners, which is the point: a system with the best expectancy and a
ruinous drawdown wins under `Expectancy` and loses under `Drawdown`. "Best" depends on what is being asked,
and §48 exists because one number cannot carry that.

`Consistency` is now **one objective among seven** rather than the meaning of "best" — `rank-setups.py` has
always sorted on positive-period share and worst period, and that is now a named choice instead of an
assumption baked into the only sort that existed.

### Two ways a ranking lies, both closed

* **An unmeasurable row must not win by being unmeasured.** A row missing the sort key, or carrying §39's
  `unavailable()` marker, sorts **last** — including on a *minimised* key, where a missing value would
  otherwise read as "zero drawdown". That case has its own test.
* **A row that cannot supply one of §48's seven exposures is ranked and MARKED, never dropped.** Dropping it
  hides a system; ranking it silently hides that the comparison is uneven.

### §49: the A/B refuses rather than caveats

The six things §49 says to hold identical **are** the experiment. `ab()` raises when the arms differ on any of
them and names which — rather than reporting with a caveat, because a caveat on a two-column table is not
read. Each of the six has its own test.

`ab()` reaches **no verdict**. §49 says the filter must not be *assumed* to improve performance, which means
the comparison must be able to conclude that it does not — so `opportunity_loss` and `missed_opportunities`
(the filter's **cost**, from §41's evaluation states) are reported beside expectancy and drawdown. An A/B that
reports only the benefit side can only ever flatter a filter.

An undeclared context item is reported as undeclared rather than assumed equal.

`scripts/ranking.py` is the reader; `scripts/tests/test_ranking.py`, 32 tests.

## 55. A polling feed goes stale differently (CLAUDE.md §52, 2026-09-18)

§52 is written for a WebSocket and this repo has none: crypto is Binance REST polling, CFD is an MT5 file
export. Four of its ten requirements — connection lifecycle, heartbeat, reconnect, exponential backoff — are
genuinely about a connection nobody opens.

They are declared `not_applicable` **with the reason and with what would make them apply**, and the loader
refuses an exemption missing either. An exemption that outlives the transport justifying it is how a
requirement quietly disappears, and "N/A" with no reason is indistinguishable from "not done".

The sentence that survives any transport is the one with teeth:

> "Do not trade from silently stale state."

The word is **silently**. §20 catches everything wrong *inside* one response — a duplicate bar, a hole, a
backwards timestamp, a stale `last_updated`. What nothing caught is the faults that only exist **between**
polls, each of which returns a response §20 finds perfectly valid:

| fault | what it looks like |
|---|---|
| `STALLED` | the series stopped advancing while wall clock moved past several bars |
| `GAPPED` | this poll starts *after* the previous poll's newest bar — the bars between were never seen |
| `REGRESSED` | the newest bar went backwards, or the bar count collapsed |
| `REVISED` | an already-closed bar came back with different values — §8's provider correction, **arriving live** |

`UNKNOWN` is **not healthy**: the first poll after a restart knows nothing, and treating that as health is how
a restart launders a stalled feed. The registry loader requires that sentence to be present.

### Two false positives shaped the stall detector, and both came from running it

1. **Identical polls inside one bar are normal.** The first version counted consecutive identical responses.
   Three dry ticks inside a minute marked **all 32 feeds stalled** — a 15m feed polled three times inside one
   bar is *supposed* to return the same closed bars. A stall is measured against the **bar**, not the poll.
2. **`last_updated` advancing while bars stand still is normal *here*.** The second version treated that as
   "the source is claiming freshness it does not have" — a real failure mode, and not this repo's:
   `fetch-binance-klines.sh` stamps `last_updated` with the **fetch** time, so it advances on every poll by
   design. That version marked **all 28 crypto feeds stalled**. Reading the field's name would not have shown
   this; running it did.

What survives is the signal that depends on neither: enough wall clock has passed that a new bar must exist,
and none does. Both false positives are pinned as tests so neither rule can come back.

### Feed health feeds the existing gate, it does not become a new one

> §52: "Realtime data quality must feed into the same data-quality and required-analysis rules used by the
> Decision Engine."

`as_quality()` maps each feed state onto §20's own vocabulary — `STALLED → STALE`, `GAPPED → PARTIAL`,
`REGRESSED`/`REVISED` → `INVALID`, `UNKNOWN → UNKNOWN` — and hands it to `_require_quality`, where the
**stricter of the two states decides**. There is no gate in `feed_health.py` and a test asserts there is none:
a second, quieter gate would be a second place for an entry to be allowed.

A replay is not observed — poll-to-poll health is meaningless over one stored file and would mark every
research run stalled — and an observation failure never fails a tick (§1 puts execution safety above
measurement).

`scripts/feed_health.py` is the tracker; `scripts/tests/test_feed_health.py`, 28 tests.

## 56. The decision log, and the sentence most decision logs drop (CLAUDE.md §53, 2026-09-18)

§53 asks for eight fields per decision. The repo had dated decisions — in `SYSTEM-DESIGN.md` sections, in
`docs/specs/*` `## Decisions` blocks, in audit rows — and **no single place to look**. "Has this been
decided?" had no answer that was not a grep, and "was this alternative already rejected, and why?" had no
answer at all.

The second question is the expensive one. An alternative re-proposed and re-rejected costs the same as the
first time, and §53's last sentence is the only part of an ADR format that addresses it:

> "When an alternative has been rejected, do not repeatedly reopen it unless new evidence appears."

That is **not satisfiable by a document**. It needs an index of every rejected alternative and something that
can be asked. `rejected_alternatives()` builds the index (32 entries across the 11 seeded decisions) and
`check_reopening()` raises, naming the ADR, its date and the original reason.

**Reopening takes the evidence itself, not a flag.** A boolean would let anyone re-litigate by passing
`True`; `new_evidence` is a string that goes on the record with the reopening. §53 permits reopening — it
forbids reopening *repeatedly without new evidence*, and those are different rules.

### Two format decisions

**Markdown with frontmatter, not JSON.** §53's fields are prose — context, reason, consequences — and prose
in JSON is unreadable in a diff, which is where a decision log is actually read.

**ADRs point, they do not restate.** The design detail lives in `SYSTEM-DESIGN.md`; the ADR carries §53's
eight fields and a pointer. Restating would create a second copy that goes stale the first time the design
changes — the failure `rules/single-source-of-truth.md` exists to prevent. A test requires at least eight of
the eleven to point rather than duplicate.

### The validator has opinions

`alternatives` being empty is refused with its own message: *a decision with no alternatives considered was
not a decision, it was a default.* `rejected_alternatives` being empty is refused with a different one,
because that field is what stops the same alternative coming back. Every one of the eight is tested by
emptying it in turn.

The index is **generated** (`scripts/adr.py index`) and a test asserts the committed `docs/adr/README.md`
equals the generated output — a hand-edited index is a second source.

### What is in the log

The eleven seeded decisions are the load-bearing ones of this work: the registry/reader/drift-test pattern
itself, required-ness not being inheritable, the decision ordering as a walk, PIT proved by attack, the
flag-vs-invalidate line, no universal score, three-valued evaluation states, immutability three ways,
one-way OOS exposure, NOT_RUN counting against, and exemptions naming their own expiry.

`scripts/adr.py` is the reader; `scripts/tests/test_adr.py`, 20 tests.

## 57. The coverage audit is a registry, and every citation is opened (CLAUDE.md §54 + §55, 2026-09-18)

§54 and §55 are the two sections a repository cannot self-report on. Both had been audited by hand — 18 of
29 invariants, "14 of 38" adversarial cases — and a hand audit is accurate on the day it is written and
never again. That one had already drifted twice over: several of its "uncovered because the feature does not
exist" entries described features that now exist, and its denominator was wrong (§55 lists **52** cases, not
38).

So the audit became `docs/architecture/test-coverage.json` and `scripts/tests/test_coverage.py` is the one
reader. Three properties make it worth more than the prose it replaced:

**The lists are parsed out of `CLAUDE.md`.** The 29 §54 invariants and the 52 §55 cases — in six groups,
in the spec's own order and wording — are compared against the spec text itself. A new bullet in either
section fails here rather than being noticed a year later.

**Every citation is `path::test_function`, and the checker opens the file.** This is the whole difference
between a coverage registry and a list of good intentions: a citation naming a renamed or deleted test
fails. It earned its keep on the first run, rejecting roughly thirty citations in the first draft that named
plausible tests which do not exist.

**Uncovered is a value, with a reason.** `covered: false` is legal, but the entry must carry a `_why`,
because "not written yet" and "cannot be written because the feature does not exist" are different facts and
only one of them is a to-do. Both lists currently have none of either.

### The critical invariant

§55 ends with one sentence that outranks the 52 cases above it:

> A required analysis failure must never silently become an optional analysis.

The previous audit recorded it as **untested, and untestable — there was no classification field to assert
on**. §35 created one, and it now has three separate guards, cited separately because three citations of the
same test would be one guard wearing three names:

| Guard | What it stops |
|---|---|
| `test_there_is_no_runtime_reclassification` | `reclassify()` exists only to raise — no code path can move an input between classes at runtime |
| `test_a_baseline_role_of_required_refuses_to_load` | a registry that declares a REQUIRED baseline role, so required-ness could be inherited and then lost, refuses to load |
| `test_assert_may_gate_refuses_every_non_gating_role` | only `REQUIRED_FOR_DECISION` can gate; the other three roles raise if asked to |

### And §54's own instruction

> "Prioritize invariant-focused tests over arbitrary global line coverage."

Checked as an absence: a test asserts no `fail_under` or `--cov-fail-under` appears in any config file in
the repository. A line-coverage gate is the thing §54 says not to prioritise, and having none is the
evidence.

`scripts/tests/test_coverage.py`, 17 tests, over a suite of 1650.

## 58. The only section that is satisfied on a screen (CLAUDE.md §50, 2026-09-18)

Every other section in this specification can be satisfied by a module. §50 cannot. A field can be computed
correctly, carried with its provenance intact, gated on correctly — and never rendered, and nothing else in
the repository would notice. The previous compliance row was a 22-field hand audit that found six missing, and
a hand audit is right on the day it is written and never again.

So §50's own list is `docs/architecture/ui-fields.json`, `scripts/ui_contract.py` is the one reader, and each
field names a **marker** the page emits as an attribute:

```html
<div class="ctx-v" data-ui-field="execution-venue">binance_futures</div>
```

`scripts/tests/test_ui_contract.py` **builds all four pages** — both chart styles, the control panel, the
journal — and audits them. A field cannot be marked exposed by editing the registry; only by rendering.

### What was actually missing

Six fields, now rendered in a context strip above the charts, each from the registry that already owned the
value:

| Field | Reader | What it now says |
|---|---|---|
| Market type | `instruments.market_types` + `providers.data_market_type` | `SPOT read · PERPETUAL traded` |
| Data provider / Source venue | `providers.for_role` / `venue_of` | `binance_public` / `binance` |
| Execution venue | `providers.unattended_venue_for` | `binance_futures` → `futures` |
| Event risk | `event_risk.state` | the state **plus its as-of** |
| Account profile | `account_profile.for_venue` | `pilot-binance-futures-testnet` |
| Risk | `trading_env.MAX_RISK_PCT` | `1% of equity per trade` |

The market-type cell prints **both** values on purpose. The crypto page draws SPOT candles while the pilot
trades a PERPETUAL — a divergence this repository has had on record since §20.1 and which no page had ever
said out loud. One word would have hidden it.

### Two things the design refuses

**A literal is not exposure.** Every field names the reader that supplies it, and a test greps
`context_strip()` for hard-coded venue and market-type strings. A page that says PERPETUAL because someone
typed PERPETUAL is asserting, not exposing, and it keeps asserting it after the venue changes.

**Required and optional may not render identically.** §50 asks that required analysis be visually
distinguishable from optional; §62 says why — only `REQUIRED_FOR_DECISION` may gate an entry. The registry
gives each a `distinguishable_by` class and the **loader refuses them being equal**, because making them the
same is the one edit that would invert the section while looking like a tidy-up. The split itself comes from
`trading_system.classification()` — the same call the order path makes — so the page cannot show one split
while the runner uses another. On the crypto page today: required **ICT**; not required **Footprint ·
Heatmap · Wyckoff**.

### Point-in-time on a static page

A published artifact is a snapshot. Event risk and data quality therefore carry their own as-of stamp and the
strip's header says so. An event-risk line with no as-of is a claim about *now* made by a file written hours
ago — §20's "never silently convert STALE to FRESH", happening on a screen instead of in a gate.

### The two areas with no page

§50 names four core UI areas. **Trading Control Center** is the method panel (the active configuration) plus
the chart page (the running analysis over it) — two pages, which is the strongest form of the distinction §50
asks for. **Trade Journal & Performance** is the journal. **System Lab** and **System Performance & Ranking**
have no page: candidate generation is markdown under `docs/backtests/` plus the §42 record store, and §41
cannot approve any proposal today because no period in the repository can validate one (§44). Both are
declared absent with a reason and a trigger, rather than left as silent gaps.

`scripts/ui_contract.py` is the reader; `scripts/tests/test_ui_contract.py`, 27 tests. Browser-verified over
`127.0.0.1` on 2026-09-18: crypto 22/22 with 297 canvases, cfd 22/22 with 66, panel 6/6, journal 5/5, zero
console errors, zero mojibake, both languages live.

## 59. "We don't use it" is not "it isn't there" (CLAUDE.md §51, 2026-09-18)

§51 has eight requirements. Seven were already held somewhere in this repository and had simply never been
written down together: the pilot's refusal of environment `real`, the `__FILL_ME__` placeholders, the
`unattended` provider flag that keeps the human-confirmation venue out of an unattended loop, the §36 decision
ordering, two demo-only account profiles, a venue resolution that raises instead of defaulting. Those are now
`docs/architecture/execution-safety.json`, and each names the function that holds it — **resolved** by the
tests, because a requirement satisfied by prose is not satisfied.

The eighth had no home at all, and the compliance ledger had said so since the first audit:

> Only gap: withdrawal permission is never requested but never asserted either — no key-scope check at load.

### The distinction that is the whole section

"No code in this repository calls a withdrawal endpoint" was true. It is not the same claim as "this key
cannot withdraw." A key minted with withdrawal rights would have traded exactly as well as one without, and
nothing anywhere would have said so. The difference matters exactly once — on the day the key leaks — and by
then it is the entire balance.

So the scope is read from the provider, not inferred from the code:

```
scripts/binance-testnet-order.sh api-restrictions   →  data/live/key-scope.json
```

and `scripts/execution_safety.py` gates on it, in the pilot's `automation_gate()` — the one gate that can only
stop a tick, never start one.

### Three values, and the middle one is the point

| State | Meaning | Effect |
|---|---|---|
| `NO_WITHDRAWAL` | the provider reported the restrictions and withdrawals are off | trade |
| `WITHDRAWAL_ENABLED` | the provider reported that this key may withdraw | **refuse in every environment, demo included** |
| `UNKNOWN` | unread, or unreadable | refuse in `real`; recorded, never laundered, in demo |

`WITHDRAWAL_ENABLED` refuses in demo too, deliberately. The thing being refused is what the key *can do*, and
a key that can move funds is not made safe by the intentions of the run holding it.

`UNKNOWN` is the same three-valued discipline §20 applies to data and §38 applies to research, arriving at the
last place it was missing. It is a real state here and not a hedge: Binance publishes `apiRestrictions` on the
mainnet SPOT host only, so a testnet key genuinely cannot be probed. Calling that "no withdrawal permission"
would be a lie with a reassuring shape. The loader refuses an `UNKNOWN` redefined as safe, and refuses an
empty refusal-environment list — either edit would make `UNKNOWN` indistinguishable from `NO_WITHDRAWAL`
exactly where it matters.

### What is pointed at rather than restated

§51's "before execution validate" list — market, instrument, market type, provider capability, account, risk,
event risk, order constraints, execution configuration — is the §36 decision ordering, and that has one
source: `docs/architecture/decision-order.json`, seventeen steps each naming its live and backtest
implementation. A second copy inside §51's registry would drift the first time a step moved. A test asserts
those words do not appear in this registry's structured rows.

### Not weakened

§51 is the one section where a regression is measured in money, so four tests re-verify what was already
there: the pilot still refuses `real`; a placeholder credential still refuses; there is still no account
profile for `real` (so an order path has no rules to obey and must stop); and the manual-confirmation provider
still cannot be selected by a loop with no human in it.

`scripts/execution_safety.py` is the reader; `scripts/tests/test_execution_safety.py`, 27 tests. The module
imports no network library at all — asserted, because the probe must stay a deliberate act.

## 60. The self-review, as a command (CLAUDE.md §56–§62, 2026-09-18)

Six of these seven sections were recorded in the compliance ledger as **POLICY** — its word for "true by
intention". Intentions are not checkable, and four of them turn out to be.

**§56** names nine phases and forty deliverables. Once each phase names the artifacts that discharge it, "do
not implement future phases speculatively during earlier phases" becomes a file check. All nine have
artifacts; none is empty.

**§57** names nine speculative things *by name*, so whether any is in the tree is a scan rather than an
opinion. Six are scanned for by marker — docker-compose, Dockerfile/k8s/helm, celery/kafka/rabbitmq,
zookeeper/etcd/consul, terraform/boto3/cloudformation, sqlite3/psycopg/sqlalchemy/redis — and find nothing.
Two are answered by tests that already existed. One, "abstractions", is declared unscannable with a reason: an
abstraction is unnecessary only relative to what uses it. The scan is mutation-tested against a planted
`import celery`, because a scan that has never found anything is indistinguishable from one that cannot.

**§58** asks for ten things and forbids nine. Five of the nine forbidden ones were already pinned by a test
somewhere and nobody had collected them, so nobody could say which of the rest are conventions. Now each rule
carries its test or an explicit `null`. "Meaningful names" has no test; claiming one would make the ten real
ones worth less.

### §60 is the section that pays for the rest

Thirty-five questions — *is PIT preserved?*, *can optional analysis accidentally block?*, *can AI modify
production silently?* — every one of which this suite already answers. Nothing had collected them, so the
self-review was a promise.

```
python3 scripts/policy.py --review
```

prints all thirty-five with the citation that answers each, and the suite fails if any stops resolving. Two
details make it a review rather than a self-assessment:

* **The answer is not the check.** Each item declares the answer §60 requires *and* the test that produces it.
  The answer alone would be a second claim.
* **The two question shapes are kept apart.** "Is PIT preserved?" must answer YES; "Can required analysis
  accidentally be bypassed?" must answer NO. A test enforces the polarity, because answering YES to one of the
  second kind is a finding, not a pass.

Ten of the thirty-five cite a §54 invariant **by name** and resolve through `test-coverage.json`, so the
repository keeps one citation list, not two.

### §59's uncomfortable half

> "Never make a local implementation change that silently changes historical research semantics."

The word is *silently*. Such changes are allowed; what is forbidden is making one quietly. Four changes in
this repository did exactly that kind of thing, and each is now recorded with what it invalidates — the loader
refuses one that does not say:

| Change | Invalidates |
|---|---|
| §37 R:R floor moved to **net** of fees | every backtest and ranking produced before 2026-09-18 is not comparable with a later one |
| §34 risk ceiling unified at 1 % | position sizes in pilot records written before 2026-09-17 |
| §33 `max_positions` derived across the venue (4 → 11) | nothing yet — forex is `default_enabled: false` |
| §23.1 MT5 CFD history replacing the Yahoo futures proxy | **DONE 2026-09-18** — every CFD backtest and ranking before that date measured a futures contract; regenerated the same day. 2H/30m/5m stayed on the proxy and are now a §38 FLAGGED provider mix |

A test asserts the pending one is recorded as pending rather than as done.

### §62

Unchanged, and deliberately not a second list: §62 restates §55's last sentence as the platform's final rule,
so `policy.json` cites the **same three guards** `test-coverage.json` does, and a test asserts the two lists
are identical.

`scripts/policy.py` is the reader; `scripts/tests/test_policy.py`, 30 tests.
