---
title: The decision and the chart read one structure source; chart images are a verification gate, never a decision input
date: 2026-09-28
status: ACCEPTED
context: The platform computes ICT and Wyckoff structure twice. The decision path (the backtest and the live runner) uses scripts/ict-scan.py, scripts/wyckoff_rules.py and scripts/live_rules.py and recomputes structure on every bar. The chart path (scripts/build-artifact.py + scripts/chart.js) has its own ICT detector in chart.js and draws the Wyckoff range, events and phases from a once-a-day model read (data/live/narrative/, data/live/anchors.*.json). The 2026-09-28 fidelity audit (docs/audits/2026-09-28-method-fidelity.md §1, §3) found that the two ICT implementations differ on old pools, sweep state and MSS handling, and that the live Wyckoff levels were carried forward for 17 days. The owner reported the same thing from looking at the charts. The owner then proposed a pipeline of read data -> draw chart -> verify the chart -> reason from the chart image -> decide, and asked which design is better.
problem: With two independent structure computations, the chart a person reviews is not the analysis that decides, so a correct-looking chart can hide a wrong decision and the reverse. Nothing forces the two to agree, and the live chart can go stale while the decision path does not. On the other hand, deciding from a chart image would make every decision depend on a vision model's reading of pixels.
decision: |
  1. ONE structure source. Structures (pivots, liquidity, sweeps, MSS, FVG, dealing range, bias; Wyckoff trading range, events, phases) are computed once, by deterministic code, from point-in-time data. The decision engine and the chart both consume those same objects. The chart only renders them and never re-derives structure of its own. A structure the decision path does not compute is not drawn as if it were analysis.
  2. Chart images are a VERIFICATION GATE. scripts/capture-charts.mjs captures the rendered charts, and an independent reviewer judges them against knowledge/. This runs periodically, after any methodology code change, and on the setups under review. A defect it finds is fixed in the structure code, so the backtest and the live path inherit the fix.
  3. A chart image is never a decision input. Optionally, in human-confirmation mode, a failed chart check may BLOCK an entry. It never creates or sizes one.
alternatives:
  - Keep two parallel paths (data -> decision; data -> chart) as today.
  - The owner's proposal -- data -> chart -> verify chart -> reason from the chart image -> decision.
chosen_approach: One deterministic structure computation feeding both the decision and the chart, with image review as an audit and blocking gate outside the hot path.
reason: A decision made from images is not reproducible or backtestable over years of bars, and is not point-in-time provable (CLAUDE.md §9, §37, §46). Pixels lose the exact prices that entries, stops and FVG edges need, and §40 forbids an LLM as a mandatory hot-path dependency. The owner's underlying goal -- what is seen is what is decided -- is met exactly by one source rendered faithfully, and the image check keeps the part of the proposal that catches drawing and detection errors.
consequences: |
  chart.js's own ICT detector and the model-read Wyckoff overlay are replaced by rendering the engine's structure objects. The model read keeps only its narrative role and no longer owns levels that are drawn as analysis.

  The build must obtain structure from the same code and point-in-time state as the decision. That is a shared-contract change (§59), implemented and reviewed as its own step.

  A methodology change that alters structure changes both the decision and the chart, so version significance (§47, §59) is assessed once.

  Image review needs a Chrome runtime (scripts/capture-charts.mjs) and reviewer runs. It does not run on the hot path.
rejected_alternatives:
  - Two parallel structure computations -- rejected; they already disagree (fidelity audit §1.1 I-chart items, §3), and nothing forces them to agree.
  - Deciding from a chart image -- rejected; the decision would be non-deterministic, not backtestable or reproducible, lossy in price precision, and dependent on an LLM on the hot path (§40). It would also inherit every drawing error instead of catching it.
---

Design detail and implementation plan: to be written after the method diagnosis (docs/audits/2026-09-28-method-diagnosis.md) and the chart visual reviews (docs/audits/2026-09-28-chart-visual-review-*.md) are in, so that the one structure source is built with their findings.
