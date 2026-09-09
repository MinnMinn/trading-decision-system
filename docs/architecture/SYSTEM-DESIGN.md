# Institutional Trading Decision System — Architecture (v1)

Status: v1, adversarially reviewed (fork review, 2026-09-09) — one critical scoring-math bug found and fixed (§6.2), plus 6 smaller gaps closed (mode-lock, anti-cherry-picking, throttle reset, event calendar, risk config, rollup format). See inline "added after review" notes below for exactly what changed and why.
Owner spec: the master system prompt (institutional trading decision system, Wyckoff + ICT/TTrades + Footprint + Heatmap, capital preservation first).

This document is the single source of truth for how the system's Skills, Agents, Commands, and Hooks fit together, and how data flows from raw sources through validation, methodology analysis, confluence scoring, risk checks, to a trade decision and its journal record. Skills/Agents/Commands files reference this document rather than restating it (per single-source-of-truth discipline) — if this doc changes, those files should NOT need to change their own text, only their behavior.

---

## 1. Design principles carried over from the master spec

- Capital preservation > decision quality > consistency > expectancy > continuous improvement, in that order, always.
- Confluence Score (0–100) is a **decision-quality** measure, not a win-probability estimate, until statistically calibrated.
- Missing data is never confirmation. A methodology requirement that cannot be evidenced is a failed requirement, not a neutral one.
- Analysis and execution are separately permissioned. `/execute` is the only command that can even attempt to move toward a live action. **Stage 1 (built, `scripts/binance-testnet-order.sh`, verified end-to-end against real Binance SPOT TESTNET order matching):** it can place real testnet orders, but only after one explicit human confirmation per trade, only on BTCUSDT/ETHUSDT/SOLUSDT LONG setups, and never from an unattended/scheduled context (§9).
- No Forex, ever. No instrument outside {BTC, ETH, SOL, XAUUSD, XAGUSD, USOIL/UKOIL} without explicit user approval.

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

- **Crypto market data — LIVE.** `scripts/fetch-binance-klines.sh` pulls real Binance public REST data (no API key needed), verified against BTCUSDT/ETHUSDT/SOLUSDT. Written to `data/live/market-data/`.
- **Commodities market data — bridge built, untested against a real terminal.** An MT5 file-bridge (`integrations/mt5/ExportOHLCV.mq5` writing to `data/live/mt5-bridge/`) replaces the earlier "third-party provider TBD" plan — see `docs/architecture/mt5-bridge.md`. Caps XAUUSD/XAGUSD/USOIL/UKOIL analysis at 2 of 4 dimensions (Wyckoff + ICT only — Footprint/Heatmap need CoinGlass, which doesn't cover commodities), so NORMAL mode is the ceiling for these instruments until an order-flow source for MT5 markets exists. TradingView MCP was considered and dropped: TradingView has no official public data API, and the community MCP servers for it rely on browser automation or unofficial scraping. See `docs/architecture/data-sources.md` for the full rationale.
- **CoinGlass** — footprint history, liquidation heatmap, orderbook heatmap, delta/CVD, open interest, funding. No API key configured yet — still MOCK.
- `mock/market-data/` and `mock/coinglass/` remain available for deliberate rehearsal runs even after real connectors exist — same field shape, so Skills never change regardless of which mode is active.
- **Every** Data Validation Status report (§4.1 in WyckoffSkill/FootprintSkill/HeatmapSkill, and the shared status block emitted by every command) MUST show a 4th state, **MOCK**, distinct from AVAILABLE/UNAVAILABLE/STALE, whenever fixture data is in use — this is a hard rule, not a style choice, so a mock-mode run can never be mistaken for a live-confirmed one. See `docs/architecture/data-sources.md` §"Mock-mode integrity rule".

## 4. Skills (7)

| Skill | Owns | Reads |
|---|---|---|
| **WyckoffSkill** | Phase ID, Spring/Upthrust typing, Trading-Range/fractality reads, Effort-vs-Result, SOT | `knowledge/07-wyckoff-and-modern-tools.md`, `knowledge/01-03` (Footprint course's Wyckoff content) |
| **ICTSkill** | Market structure (MSS/BOS/CHOCH/CISD), OB/FVG/Breaker/Mitigation, liquidity (IRL/ERL), OTE, premium/discount, killzones, SMT, PO3/AMD, TTrades models | `knowledge/04-06` |
| **FootprintSkill** | Order-flow read: POC, R/H/R/L, Imbalance/Stacked Imbalance, Absorption/Exhaustion/Development, Delta/Cumulative-Delta divergence, Tape Reading (Bar-by-Bar/Analog/Swing-by-Swing) | `knowledge/01-03`, `knowledge/07` §3 |
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

Methodology Mode minimums (unchanged from the master spec): NORMAL ≥2, ENHANCED ≥3, STRICT ≥3 explicitly-selected + zero unresolved high-impact contradictions. If the count is unmet, DecisionAgent must return **NO TRADE**, full stop — it may not add a methodology just to reach the count (hard rule).

### 6.2 Confluence Score — rubric

**Corrected after adversarial review — the first draft had a critical bug: capping every dimension at 25/100 flat made the STRICT-mode 85 threshold mathematically unreachable with only 3 dimensions engaged (3×25=75 max), silently forcing all 4 dimensions every time and contradicting the master spec's own "3 or more" wording. Fixed by scoring against the *engaged* maximum, not the flat 0–100 scale:**

1. Each dimension a Skill actually analyzes (regardless of mode) gets 0–25 raw points from its own evidence checklist below, but is only **eligible/"engaged"** if its data source is `AVAILABLE` (not `MOCK`/`STALE`/`UNAVAILABLE`) per §6.1. Unavailable or not-analyzed dimensions score 0 and do not count toward `engaged_count`.
2. `raw_pct = (sum of points across engaged dimensions / (engaged_count × 25)) × 100` — e.g. 3 engaged dimensions scoring 22/25 each → raw_pct = 66/75 × 100 = **88**, correctly clearing STRICT's 85 threshold; if `engaged_count = 0`, `raw_pct = 0`.
3. Subtract the **Contradiction Penalty** (percentage points, not raw points) from `raw_pct`: major opposing HTF structure (−15), major opposing liquidity/liquidation cluster (−10), event-risk within the pre-event blackout window (−20, and independently forces NO TRADE regardless of score — see §6.3). Multiple contradictions stack; floor at 0.
4. `final_score = max(0, raw_pct + penalty_total)`, where `penalty_total` is the (negative) sum of contradiction penalties in percentage points — e.g. `raw_pct = 82`, one high-impact contradiction `penalty_total = −20` → `final_score = 62`. (Sign convention matches `schemas/confluence-score.schema.json`: `penalty_total ≤ 0`.) Compare against the flat mode threshold (70/80/85) — this comparison is now meaningful at any engaged-dimension count.

Per-dimension partial credit (illustrative point allocation inside each dimension's 25; a Skill's own procedure is the authority on what evidence maps to which bucket):
- **Wyckoff (25):** phase clarity (0–8), Spring/Upthrust type & quality (0–10), Effort-vs-Result / SOT alignment (0–7).
- **ICT (25):** HTF bias alignment (0–8), structure/location quality — OB/FVG/liquidity/OTE (0–10), timing — killzone/PO3/AMD alignment (0–7).
- **Footprint (25):** absorption/exhaustion/development read (0–10), Delta/Cumulative-Delta divergence strength (0–8), Tape-Reading case alignment (0–7).
- **Heatmap (25):** liquidity-sweep/target alignment (0–10), liquidation-cluster interaction (0–8), orderbook positioning (0–7).

**Score threshold AND dimension-count minimum are both required, independently** — `dimension_count_met` (engaged_count ≥ mode minimum) is a separate boolean gate from `threshold_met` (final_score ≥ mode threshold). `verdict = TRADE` requires **both** true, plus no blocking event-risk contradiction. This still closes the original loophole (one dimension alone can't "buy" a pass, since a lone engaged dimension can never meet a ≥2 count minimum) without breaking STRICT mode's math.

**Anti-cherry-picking rule (added after review):** a trader/agent may not simply stop analyzing once the mode minimum is reached while leaving other *available* data unchecked. Contradiction Analysis (§7 of the master spec) MUST run against **every dimension whose data source is `AVAILABLE`**, not just the ones counted toward the minimum — an available-but-unengaged dimension's contradictions still apply their full penalty. Only a dimension that is genuinely `UNAVAILABLE`/`STALE`/`MOCK` is exempt from this contradiction sweep, because there is no evidence to check.

**Mode-lock (added after review, closes a missing master-spec hard rule):** DecisionAgent must select and record `methodology_mode` as the very first scoring step, before any dimension is analyzed, and it is immutable for the rest of that analysis run — never downgraded after the fact to make a weak result pass (master spec §3/§9).

### 6.3 Regime and Event-Risk gates (run before scoring, not after)
- Market Regime = TRENDING / RANGING / TRANSITIONAL / UNCLEAR, per StructureAgent's read. If UNCLEAR and the candidate setup is regime-dependent (e.g. a range-Spring thesis inside what might actually be a strong trend), DecisionAgent must reduce the Wyckoff/ICT dimension credit or return NO TRADE — never silently assume RANGING.
- Event Risk = HIGH / MODERATE / LOW, checked against **`docs/architecture/event-calendar.md`** — a small, human-maintained list of upcoming high-impact events (CPI, FOMC, NFP, Fed speeches, EIA/OPEC, major scheduled crypto events) with dates and blackout windows. This file has no automatic feed in v1; the user (or LearningSkill, via `/improve`, never silently) updates it. If the file is stale (no entry covering the current date) or absent, Event Risk must be reported `UNKNOWN`, not `LOW` — an unmaintained calendar is a data-quality gap, not a clean bill of health. HIGH inside the pre-event window forces the −20 penalty above regardless of everything else, and should usually still resolve to NO TRADE / WAIT even at a high raw score, per the master spec's explicit "never treat technically perfect pre-event structure as automatically safe."

## 7. RiskAgent / RiskSkill — position sizing and hard limits

Inputs: account equity and default risk % are read from **`docs/architecture/risk-config.json`** (a small user-edited config, so they don't need to be re-supplied on every call), overridable per-command with an explicit parameter. Hard ceiling 1%, never overridable above that without an explicit typed override that RiskSkill logs as a flagged exception in the resulting trade file. Outputs: position size, dollar risk, R:R at each target, and a PASS/FAIL against every §15 "Necessary Condition" in the master spec (clear invalidation, defined stop, acceptable R:R, etc.).

**Consecutive-loss throttle:** RiskSkill reads the last closed, **non-rehearsal** trades from `trades/*.md` (§8) — rehearsal-mode trades never count, per their schema flag — counting consecutive `result: LOSS` entries back from the most recent closed trade. After 2 consecutive losses, it must recommend halving size or pausing, per the master spec §20. **Reset condition (added after review — the first draft left this undefined):** the throttle deactivates the moment either (a) one subsequent trade closes as a `WIN`, restoring normal risk %, or (b) the user explicitly overrides via `/risk` with a logged reason. Absent either, the throttle stays active indefinitely — it does not silently expire after a time window.

Hard, non-negotiable checks RiskAgent performs on every `/analyze`, `/entry`, and `/execute` call (mirrors master-spec §25 Hard Safety Rules 2–5):
- Risk % ≤ 1% — reject and recompute if violated.
- A Stop Loss and an invalidation level both exist and are distinct concepts (price vs. thesis vs. data invalidation, §21) before any BUY/SELL verdict is allowed to stand.
- No "average down," no "widen stop after entry," no "remove stop" — these are refused outright, not merely flagged, if requested via `/entry` or `/execute` on an already-open position.

## 8. JournalSkill — storage design

No database exists in v1. One Markdown file per trade under `trades/<YYYY-MM-DD>-<PAIR>-<seq>.md`, YAML frontmatter matching `docs/architecture/schemas/trade-file.schema.json`, body = the full Decision Output (master spec §23) at plan time, appended with the Post-Trade Review (§26) fields at close time. This single file **is** the Journal entry, the Edge-Log entry, and — if flagged — a Mistake-DB entry.

**Rollup mechanism (made concrete after review — "queryable" was hand-wavy in the first draft):** JournalSkill regenerates **`trades/index.jsonl`** on every `/journal` or `/status` call — one JSON line per trade file, containing exactly its YAML frontmatter, rebuilt by scanning `trades/*.md` fresh each time (never hand-edited, always derived). `docs/edge-log/EDGE-LOG.md` and `docs/mistakes/MISTAKE-DB.md` are then simple filtered/formatted views over `trades/index.jsonl` (e.g. Edge Log = every closed, non-rehearsal trade sorted by date; Mistake DB = every trade with `is_mistake: true`, grouped by `root_cause`) — cheap to regenerate, never a second hand-maintained copy of the data. This is a deliberate simplification from the master spec's three-named-artifact language — same information, one source of truth, per this project's own single-source-of-truth rule. `trades/README.md` documents the format.

## 9. Commands (11)

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
| `/execute` | Separately-permissioned; see below | **Stage 1 — built and verified.** (a) requires one explicit human confirmation per trade, distinct from a prior `/analyze` TRADE verdict, (b) re-runs RiskAgent's hard checks one last time, (c) on confirmation, submits a real market-buy + OCO exit bracket to **Binance SPOT TESTNET** via `scripts/binance-testnet-order.sh` (fake funds; verified against real order matching, not a simulation). Scope limits: testnet only, LONG-only (no spot shorting), BTCUSDT/ETHUSDT/SOLUSDT only, never runs unattended — a scheduled/cloud context may flag a candidate but the human-confirmation step always happens interactively. Mainnet, MT5 execution, or removing the per-trade confirmation (Stage 2) are all separate, larger decisions requiring their own explicit authorization and, for mainnet, Security review. |

## 10. Hooks — honest mapping to what Claude Code actually supports

The master spec's 7 "hooks" are a mix of two different things, and this design keeps them distinct rather than pretending all 7 are literal tool-call hooks:

- **Real Claude Code hooks (2 — one added after review):**
  1. `SessionFilterHook` → an actual `SessionStart` hook (`.claude/settings.json`) that reminds the assistant, at the start of every session in this project, of the hard safety rules, the instrument allowlist, and the Forex prohibition.
  2. `PostDecisionJournalHook` (partial) → an actual `Stop` hook that prints a plain-text reminder at the end of every turn: *"If a TRADE/WAIT/NO_TRADE verdict was just produced, confirm it's recorded via `/journal`."* **Scoped honestly:** this is an unconditional nudge, not a verified enforcement gate — a Claude Code `Stop` hook shell command cannot reliably introspect "did this turn output a verdict" without fragile transcript-text matching, so this design does not pretend it can block a missed journal entry, only remind every single time. The real enforcement is still the workflow-embedded step below (every `/analyze` run's own procedure ends with a `trades/` write as a mandatory step) — the hook is a second-layer safety net, not the primary mechanism.
- **Workflow-embedded gates (the rest):** `PreAnalysisValidationHook`, `ConfidenceThresholdHook`, the full `PostDecisionJournalHook`, `InvalidationMonitorHook`, `PostTradeReviewHook`, `LearningUpdateHook` are implemented as explicit, mandatory steps inside the relevant Command/Skill/Agent (e.g., `/analyze`'s own procedure both opens with Data Validation and closes with "write to `trades/`" as literal numbered steps) rather than as separate harness hooks — Claude Code has no market-data-push or open-position-polling event to hook into, so a "monitor" hook is realistically a recommended periodic `/invalidate` call (optionally via the `loop` skill on a schedule the user chooses), not an automatic background trigger. Documenting this honestly avoids the "hidden state" / "unexplained scoring" anti-patterns the master spec itself warns against in §33.

## 11. Learning governance (unchanged from master spec, restated as an implementation note)

LearningAgent may propose changes to scoring weights, thresholds, or methodology rules, always via the `/improve` command's KEEP/TEST/ADOPT/REJECT template (master spec §31). It may **never** directly edit: the 1% risk ceiling, the Forex prohibition, the instrument allowlist, the stop-loss/invalidation requirements, or the Analysis≠Execution separation — those live in this document (§1, §7, §9) and in the hard-coded checks inside RiskAgent, not in data LearningAgent can rewrite. Any proposal touching those requires the human to edit this document directly.

## 12. Open items / explicit gaps (do not silently resolve these)

1. **No Heatmap source document** exists in `docs/` — HeatmapSkill's rules come only from the master prompt text, not from an ingested reference. If the user adds a Heatmap/liquidity book or course to `docs/`, ingest it before trusting HeatmapSkill's outputs at STRICT mode.
2. **CoinGlass is still MOCK** — no API key configured yet. Crypto market data itself is now LIVE (Binance connector, verified). The MT5 commodities bridge is built but **untested against a real terminal** — see `docs/architecture/mt5-bridge.md` for what to check when you try it. No `/analyze` output using MOCK/untested sources can be treated as a live, tradeable signal; every such output must say so plainly.
3. **XAUUSD/XAGUSD/USOIL/UKOIL are structurally capped at NORMAL mode** even once the MT5 bridge is live and CoinGlass is connected — Footprint and Heatmap dimensions have no data source for commodities (CoinGlass is crypto-derivatives-only), so only Wyckoff + ICT (2 of 4 dimensions) can ever be engaged for these instruments in the current design. This is a structural limit, not a temporary gap — closing it would require finding or building a genuine order-flow/liquidity source for MT5 markets.
4. **Stage 1 execution is live on Binance SPOT TESTNET only** (`scripts/binance-testnet-order.sh`, credentials in macOS Keychain via `scripts/get-secret.sh`) — mainnet and MT5 execution remain unbuilt by design; wiring either is separate, larger scope requiring explicit authorization and, for mainnet specifically, Security review first (real credential/secret-handling + real financial trust boundary, not a demo).
5. **Account equity is user-supplied, not fetched** — RiskSkill has no live balance source in v1.

### 9.x Stage-2 demo pilot (2026-09-09, user-authorised, 24 h, SPOT TESTNET)

`scripts/demo-pilot.py` is a deterministic, LONG-only pilot on Binance SPOT TESTNET (fake funds): 15m closes,
entry = discount + SSL/ERL-low sweep + bullish MSS + bullish FVG + Effort-vs-Result volume check; 0.5% risk,
25% notional cap, max 2 open / 3 per symbol per day, OCO exits, 6 h time-stop, halt after 3 consecutive
losses or −2% day. `scripts/pilot-loop.sh` runs it every 15 min; `data/live/pilot/STOP` is the kill switch;
`--report` prints realised/unrealised P&L from exchange order status. Claude Code's auto-mode classifier
refuses to *schedule* unattended order placement (correctly), so the loop is run by the user in a separate
terminal; Claude only schedules read-only reports. This pilot does not change the Stage-1 rule for mainnet.
