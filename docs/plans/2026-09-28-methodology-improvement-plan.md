# Methodology improvement plan — after the 0 / 180 prop search (APPROVED 2026-09-28 with the owner decisions in §6)

Date: 2026-09-28. Owner direction: improve the methodology, and do not move the evaluation window to rescue a bad
method (docs/plans/2026-09-27-prop-setup-search-preregistration.md §9). One structure source serves the decision
and the chart (ADR 0009). Three rounds of adversarial review challenged this plan: 27 findings [R#], then 10 more
[N#], then 3 more [M#]. Each resolution below cites its finding. The items that still need an owner decision are in §6.

## 0. Evidence

| Source | What it established |
|---|---|
| docs/audits/2026-09-28-method-diagnosis.md | Funnel and outcomes on development data (< 2024-03-01), XAUUSD / US500 / DE40, 30 slices. |
| docs/audits/2026-09-28-method-fidelity.md | Code vs knowledge/ deviations (ICT I-1..I-18, Wyckoff W-1..W-27), unsourced parameters, dead configuration, staleness. |
| docs/audits/2026-09-28-chart-visual-review-ict.md, -wyckoff.md | Image reviews of the rendered charts. ICT 47 of 51 wrong; Wyckoff 26 of 27 wrong. |

The funnel's biggest cuts, in order:
- the execution gates ("already triggered" + fill), −77 %;
- premium/discount, −54 %;
- displacement, −41 %;
- FVG, −40 %.

ICT produces about 1.5–1.9 trades per symbol-year on 1H. It is +0.21 R gross but −0.02 R net. Wyckoff is −0.35 R net, because its stops are tight and its planned R is short.

## 1. Integrity rules

1. **What is exposed.** Each period is registered in docs/architecture/research-ledger.json [R1, N1]:
   - The diagnosis data is a `development` period: XAUUSD, US500 and DE40, all history < 2024-03-01.
   - [2024-03, 2025-03) is `oos_exposed`, trigger `candidate_selection` (the prop search).
   - After 2025-03 is exposed by ADR 0008.
   - No historical window is pristine.

   The only pristine evidence left:
   - **Forward demo**, from the date a new pre-registration is sealed. It is registered as `oos_untouched` at sealing [R4].
   - If the owner chooses (§6 q1), a **cross-sectional holdout** of symbols never used for a hypothesis. The recommendation is XAGUSD and US30 (1H/4H history from 2008 and 2012). It is registered now as `final_holdout` (so `research_ledger.assert_untouched` guards it) and read ONCE, by the §4 gate only. Its pass rule, fixed before any read: net expectancy > 0 with a one-sided 90 % lower bound > 0 and at least 30 trades per method cell. Whether prop-search's per-candidate development metrics count as a read of those symbols is checked first, and the answer is disclosed.
2. **Two classes of change** [R3, N2]. **F** means ONLY that the code contradicts a sourced rule. Everything else is **V**: an extension (a new object), a choice between two sourced readings, and any unsourced size or threshold inside a sourced rule.
   - **F — fidelity correction.** Adopted because the source requires it. Acceptance is a unit test and a chart check against the source. Performance is reported and never decides whether the source is followed; rejecting a correction because it scores worse would alter the source, which ADR 0007 forbids. Each F item's funnel delta is recorded. If a delta moves trade count by more than ×1.5 either way, the owner must sign off, because that is §59 version-significant even when the change is sourced [N9].
   - **V — variant.** Gated by performance. Every value is pre-declared in §3, and every run is counted.
3. **Evidence order** [R2, R18]:
   - F items are judged on outcome-free evidence: funnel counts from scripts/diagnose-methods.py, tests, and chart images.
   - Performance is evaluated ONCE, on the adopted F set plus the pre-declared V grid (§3).
4. **Statistics** [R2, R9, N3]:
   - **Nested** rolling-origin walk-forward over the development span [M1]: V values are chosen inside each training fold only, and each test fold is scored with the values chosen on its own training fold. The lower bound is computed on the pooled test-fold trades only.
   - Each V item has one pre-declared primary metric: net expectancy per trade, in R.
   - Each walk-forward test fold needs at least 30 trades; below that the verdict is "insufficient".
   - **N** counts every comparison that could be put forward [M2]: the §3 grid of the method × the number of pre-declared candidate cells (§3, "Candidate cells"). With the recommended one cell per method, **N_ICT = 41 and N_Wyckoff = 16** (AMENDED 2026-09-30, owner decision: the B-EXIT `no_floor` value was removed, so ICT is now **29** per cell and 232 over the 8 declared cells; see docs/plans/2026-09-30-owner-decisions.md); with the alternative (four cells per method) it is 164 and 64. Prior counts (180 prop records, 30 diagnosis slices) are disclosed but not folded into N.
   - The lower bound is taken at one-sided confidence 1 − 0.10/N (≈ 99.76 % for N = 41). A gate this strict may not be reachable with the current trade frequency. That is the honest price of the variants, and it is stated, not relaxed.
   - **Stability:** net expectancy > 0 on at least ⌈2m/3⌉ of the m symbols that have development data for the timeframe, and no single trade contributes more than 25 % of total net R.
   - **Frequency:** the longest gap between consecutive trades on one pooled account is ≤ 30 calendar days in ≥ 90 % of folds (preregistration §8.3).
   - **§45 checks:**
     - Regime split: the sign of net expectancy is the same in both halves of a pre-declared ADX(14) median split.
     - Perturbation: every V value moved ± one grid step keeps the lower bound > 0.
     - prop_pass_probability ≥ 0.70 under the preregistration §8 rules.
5. **Records** [R8]:
   - Every run is a sealed record through scripts/experiment.py.
   - Every period is declared in research-ledger.json.
   - The full count is disclosed with any result.
6. **Live safety** [R5, N4]:
   - The current engine is registered as Trading System **v1** before the first change.
   - Every F or V change, and A0's cost inputs, lands behind a versioned configuration key. The key defaults to v1 behaviour on the live and pilot paths and is switched only on owner approval (§47, §34).
   - Experiments carry candidate v1.x. The accepted set is approved as **v2**, and rejected candidates stay traceable [R27].
   - A2b (stale → WAIT/BLOCK) is a declared safety fix with its own §59 version note. It only makes the system stricter.
   - The risk % (1 %) and the account rules never change here. Execution and risk-input semantics change only behind the key.
7. **Scope is pre-declared** [R25, N1]:
   - The development symbol set is the 8 CFD symbols minus any holdout (§6 q1). Results are reported per symbol, and no symbol is dropped after its result is seen.
   - 15m indices (from 2022; USTEC from 2022-07) cannot be developed on, and that is stated plainly [R2].
   - Every snapshot states its news-filter setting. The backtest's §24 blackout is verified against live before the evaluation, or the gap is disclosed [R26].

## 2. Workstream A — groundwork and one structure source

- **A0 Costs** [R6, N5]:
  - Per-symbol spread, commission and swap come from the broker's MT5 symbol specification. They are taken independently of any result, and their source is recorded. Today's figure is a flat 0.05 %/side that risk-config.json itself labels "an assumption", with no slippage and no swap.
  - The diagnosis baseline is re-priced once, and that event is recorded.
  - A0 never re-evaluates [2024-03, 2025-03) as evidence. If the 180 prop records are re-priced, the result is only a disclosed erratum.
  - The 15m-scope question waits for A0.
- **A0b Research-record honesty** [R7]:
  - `ict_target="range"` is recorded in the stability files (the 180 prop records carry `ict_target: null` and a dead `range_touches: 0`; see docs/experiments/prop-search-2026-09-27/ERRATUM-2026-09-28.md), but the scanner targets −2σ. That key is removed or renamed, and so is `range_touches`, which has no reader.
  - An erratum successor record is written for the 180. The records themselves are immutable (§42).
  - A test fails when a snapshotted option has no reader.
- **A1 Extract** into one module the structures the decision path already computes:
  - ICT: pivots, pools with their state, sweeps, MSS, FVGs, dealing range, bias.
  - Wyckoff: trading range and events.

  Acceptance is byte-identical trades for the backtest and for `strategy-runner.py --replay all`. This is a hash comparison over full history with no metric viewed, so it is not a data look. The §59 impact list (10 items) is attached. Consumers: backtest-methods, strategy-runner, live_rules, build-artifact, htf_context, check-narrative, local-eval-brief [R19].
- **A1b New objects.** These are declared as new, not byte-identical: Wyckoff phase labels; `invalidated_at` for pools and FVGs [R19]; and **higher-timeframe Wyckoff trading-range detection** (WA2-19), which W7 needs [M3].
- **A2 Render** [R20]:
  - The chart draws the A1 and A1b objects only.
  - The chart.js ICT detector and the model-owned levels (anchors, narrative TR and events) stop being drawn as analysis.
  - Lines the decision path does not compute (σ, OTE, session highs/lows, PDH/PDL) are removed or labelled VISUALIZATION_ONLY.
  - Narrative text may cite engine levels only.
- **A2b Staleness is a quality state** [R20]:
  - Higher-timeframe tiers are refreshed to the entry tier's clock.
  - A stale HTF fact that reaches a decision or the brief becomes STALE → WAIT/BLOCK (§20, §52).
- **A3 Image gate** [R21, N7]:
  - scripts/capture-charts.mjs plus an independent review, after every structure change.
  - **A3t** is new tooling: build a page from a point-in-time development window.
  - Charts are rendered for development symbols only, never a holdout, < 2024-03.
  - Reviewers judge the drawing against knowledge/, never outcomes. The live-page review is a separate operational check.

## 3. Workstream B — items in a fixed order by funnel stage, with the V grid pre-declared [R18, N2, N6]

F items are adopted on source grounds. For V items, the value sets listed are the whole grid. Each V item is evaluated one factor at a time against the adopted-F baseline, and then one combined candidate is formed from the chosen values.

The three exit parameters act on the same exit, so they form **one joint factor** (B-EXIT = B-TGT × B-H × B5, 3 × 4 × 2 = 24 value sets [AMENDED 2026-09-30: the `no_floor` value of B5 was removed by the owner (planned R:R floor 2.5 for every trade), leaving 3 × 4 × 1 = 12 value sets]) [M1]. Breakeven management, formerly config B, is a V item per method (B-MGMT, W-MGMT); config C's generic HTF gate is replaced by B4.

Per method, N = 1 baseline + the non-baseline values + 1 combined: ICT 1 + 39 + 1 = **41** (AMENDED 2026-09-30: 1 + 27 + 1 = **29** after removing the 12 `no_floor` value sets); Wyckoff 1 + 14 + 1 = **16**. Nothing is added after data is seen without a ledger event.

**Candidate cells, pre-declared** [M2]. Recommended: ONE cell per method, on one pooled account over the development symbols. That cell is **ICT 1H** and **Wyckoff 4H**; 15m waits for A0 and has too little index history. Alternative: four cells per method ({1H, 4H} × {metals, indices}), which multiplies N by 4. Only the declared cells can be put forward.

**ICT**

| # | Item | Class | Source | V values (baseline first) |
|---|---|---|---|---|
| B-EX | Entry model | V | core-a.md §2.23, R19 | IOFED · CE · Fill |
| B-PD | Dealing-range framing: R15 text (current) vs R13 diagram (swept extreme ↔ opposing pool) [R10] | V | core-a.md §2.18–2.19, R13, R15 | R15 · R13 |
| B-DISP | Displacement thresholds — sensitivity only; never selected, not in N | — | project | current · ±25 % (reported) |
| B2a | FVG inside the displacement leg, not the latest FVG | F | core-a.md §3.3 R12 | — |
| B2b | CE body-close failure of a traded FVG (a new invalidation) | F | core-a.md §2.26, R23 | — |
| B1 | Pivots 1 bar each side (ICT only) | F | core-a.md §2.5, §5 | — |
| B-POOL | PDH/PDL and session highs/lows as pools (an extension) | V | core-a.md §2.8–2.9 | off · on |
| B-RAID | Stop raid "preferred", not mandatory | F | core-b.md §2.2 | — |
| B-BUF | Stop buffer beyond the wick (R22 says only "below"; the size is unsourced) | V | core-a.md R22 | 0 · 0.1 ATR · 0.25 ATR |
| B-EXIT: target | A target point inside the −2…−2.5 σ zone (part of the joint exit factor) | V | models.md §2.1.5; core-b.md §2.12 [R11b] | −2.0 · −2.25 · −2.5 |
| B-EXIT: time stop | Time stop H (no time exit in the source; part of the joint exit factor) | V | project | H · 1.5H · 2H · none |
| B-LB | Setup lookback × K-bar expiry | V | project | lookback {12, 8, 16} × K {K, 2K} |
| B6 | Cancel the pending limit when the target trades first (a project rule based on the R3 invalidation idea) | V | core-b.md §3.1 R3 (fidelity N3) | no · yes |
| B3 | Bias timeframe: the entry TF (current) vs the TFA p5 higher-TF pairing. The deck supports both readings (it lists H1 and M15 as bias candles too) [R16, M-B3] | V | models.md §2.8; core-a.md §2.11–2.12 | entry TF · TFA p5 pairing |
| B4 | HTF level engaged before the LTF MSS; R1/R23 tension recorded | V | core-b.md §3.1 R1, R23 | tag only · required |
| B-EXIT: 2R | 2R as profit-taking, not an entry floor (ICT only; fee interaction and the OSOK source stated; part of the joint exit factor) | V | models.md rule 23 | floor · no floor (`no floor` REMOVED 2026-09-30 by owner decision; floor is 2.5R net for every trade) |
| B-MGMT | Breakeven at +1R (formerly config B) | V | WMT p272 (as used by config B) | none · BE |
| B7 | Index killzones (none for XAUUSD; DST tests) | V | core-a.md R1 | all hours · killzone only |

**Wyckoff.** An owner decision on tick volume comes first [R12d]. CFD volume is a tick count (fidelity W-27), and the book requires real volume (WMT p131–133). Either Wyckoff-on-CFD is excluded from tuning, or every result is split by `volume_kind`.

| # | Item | Class | Source | V values (baseline first) |
|---|---|---|---|---|
| W-STOP | BU/LPS stop: current vs below the Spring low | V | WMT p271 [R12a] | current · Spring low |
| W-BU | LPS[C]/BU path (80 % of trades) checked against the book | F | WA p82–84 [R12b] | — |
| W1 | TR low includes ST | F | WA p72 | — |
| W2 | ST below SC before CHoCH allowed | F | WA2-06 | — |
| W3 | A Phase-B mSOW is also a potential Spring | F | WA p91, p166 | — |
| W4a | Shakeout typing by "lingers / forms own value"; rule F, threshold V | F + V | WA p80, p83 [R14] | lingering closes ≥ 2 · 3 · 4 |
| W4b | Lower-timeframe local Spring/LPS after a Shakeout (new object) | V | WA2-12, WA2-18 | off · on |
| W5 | VP abandon rule "within 2 bars": cite or remove | F | WMT p243–249 | — |
| W6 | Structure window, decided together with ICT SCAN_WINDOW | V | fidelity §3.3 B1 | 300 · 600 bars |
| W7 | Phase-D target = the HTF TR's AR/SOS. No P&F count (WA1-06). With no HTF TR there is no Phase-D trade. Needs the A1b HTF TR detector; it acts on 80 % of trades, so **owner sign-off is required in advance** [R13, M3] | F | WA2-19, WA p83–84 | — |
| W-MGMT | Breakeven at +1R (formerly config B) | V | WMT p272 | none · BE |
| W-SPT | Spring target (current code, AR, is faithful to WA p72) | V | WA p85; WMT p273 [R12c] | AR · ceiling · VAH |
| W-TOUCH | Two tests of each TR border before a Spring counts: an unimplemented sourced rule (formerly the dead improve-loop candidate vol_type.1); a sign in the book, not a requirement | V | advance.md 2.11.2 | off · on |
| W-TW | Test window × Phase-B swings | V | project | test {12, 8, 20} × swings {2, 3} |

## 4. Going back to validation [R4, R9]

A method is put forward only when all of these hold on the walk-forward development evidence:
- the N-adjusted lower bound is > 0;
- the §1.4 stability rule is met;
- the §1.4 frequency rule is met;
- every §1.4 §45 check passes.

If the owner holds symbols out, the holdout is then read once. A NEW pre-registration is then sealed. It declares the forward-demo length and trade-count target, the budget, and the full disclosed count, before any forward trade. Historical windows serve only as disclosed, exposed checks.

## 5. Order [N8]

- **In parallel:** A0 (waits on §6 q2), A0b, A1 (byte-identical), then A1b.
- **Next:** A2, A2b, A3 and A3t.
- **Then:** F items in the §3 order, each behind the v1 key, with a funnel delta and a chart check.
- **Then:** once A0 is in, the single performance evaluation of the F set plus the V grid.
- **Last:** holdout, if any → owner review → pre-registration → forward demo.

Every item merges only after its tests pass and a code review.

## 6. Owner decisions (2026-09-28)

1. **Holdout: none.** All 8 CFD symbols are development symbols, to maximise the evidence. Forward demo is the only pristine confirmation. The `final_holdout` registration and its pass rule in §1.1 are therefore not used.
2. **Candidate cells: five.** The owner asked for the option with the best chance of finding a good setup, and "tighten later". The cells are {15m, 1H, 4H} × {metals, indices}, minus 15m indices, which has no development history before 2022. Each cell is one pooled account over its asset class.
   - This gave N_ICT = 41 × 5 = **205** (superseded: 8 cells and, since 2026-09-30, 29 per cell = 232) and N_Wyckoff = 16 × 5 = **80**, a lower bound at about 99.95 % / 99.88 %.
   - The owner's "tighten later" is honoured in one direction only. A check may be made stricter after data is seen; it may never be loosened.
3. **Costs from MT5.** integrations/mt5/ExportSymbolSpec.mq5 exports the broker's contract specification, the spread recorded on every M15 bar (per UTC hour), and the commission actually charged on the account's deals. "Always prefer what is real."
4. **Wyckoff volume matters per setup.** Wyckoff stays on CFD. Every result is split by `volume_kind`, and tick volume is labelled as a limitation, never presented as real volume. A real-volume source (for example the futures volume of the same underlying) is a separate provider decision with its own ADR, proposed later.
5. **15m stays in scope.** The owner's reason was that a $10k account makes fees small. That was corrected: a fee in R is (round-trip cost % of price) / (stop distance % of price), which does not depend on account size. 15m therefore stays in scope, judged net of the REAL costs from A0.
6. **Gate accepted** as in §4 with N from item 2: "we are building a loop to find the options that are really good."
7. **Timeframes for fund setups: 1m, 5m, 15m, 30m** (owner, 2026-09-28, after the FTMO-Demo swap export; supersedes the {15m, 1H, 4H} cells in item 2). 1H, 4H and 1D are out of the fund search.
   - **No overnight holding** is a FIXED rule in every fund cell, not a V item: a position is flat before the broker's daily rollover. This follows from the owner's reason (FTMO swaps) and costs nothing in N.
   - **Cells:** {1m, 5m, 15m, 30m} × {metals, indices}, minus any cell without development history before 2024-03-01, as established by the MT5 export. N becomes 41 × cells (ICT) and 16 × cells (Wyckoff); the final cell count is recorded in research-ledger.json before any evaluation.
   - **Data:** integrations/mt5/ExportHistory.mq5 now exports M30, M5 and M1, capped at 5,000,000 bars. M1 is stored gzip-compressed, split per year, because a single file would exceed GitHub's 100 MB limit. The FTMO symbol names are mapped with data/history/costs/ftmo/symbol-map.json.
   - **1m** has no engine parameters yet: bt.P has no "1m" entry. Its R/K/T/H are project parameters, declared before any evaluation and labelled as project-defined.
8. **AUS200 is dropped from the fund search** (owner, 2026-09-29). The FTMO-Demo export produced no AUS200.cash history, and the owner's rule was "if it is not there, drop it". The fund search uses 7 symbols: XAUUSD, XAGUSD, US500, US30, USTEC, DE40, FRA40, all from the FTMO-Demo feed. AUS200 was dropped for missing data, before any result was seen, so this is not selection on outcomes.

