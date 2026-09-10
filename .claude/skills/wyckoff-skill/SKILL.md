---
name: wyckoff-skill
description: Use when analyzing market context/narrative under the institutional trading system — Wyckoff phase identification, Trading Range structure, Spring/Upthrust typing, Effort-vs-Result and SOT reads. Invoked by StructureAgent as part of /analyze, /bias, and /entry.
---

# WyckoffSkill

Answers: **what is the market doing, and why?** Owns the Wyckoff dimension of the Confluence Score (`docs/architecture/SYSTEM-DESIGN.md` §6, 0–25 points).

Theory lives in `knowledge/08-wyckoff-and-modern-tools.md` (primary — the dedicated 374-page book) and `knowledge/01-footprint-wyckoff-logic-structure-absorption.md` (the Wyckoff content embedded in the Footprint course). This skill does not restate that theory — it tells you which section to apply, in what order, and how to score it. Cite the exact `knowledge/` section for every claim (per this project's reduce-hallucinations discipline); never assert a Spring/Upthrust type or phase from memory.

## Procedure

1. **Identify Trading Range and phase** (`knowledge/08` §2.4–2.5). Use the highest timeframe with a clean range (per the master spec's Daily+4H HTF-context step). State explicitly: TRENDING / RANGING / TRANSITIONAL / UNCLEAR for Market Regime — if UNCLEAR and the candidate setup depends on the range being real, say so; do not force a Trading Range read onto a genuinely trending chart.
2. **Classify the phase**: Accumulation / Distribution / Reaccumulation / Redistribution (`knowledge/08` §2.5). State your confidence — the source book itself says misclassifying reaccumulation-vs-distribution is one of the hardest calls; a low-confidence phase call should reduce this dimension's point allocation, not be silently treated as certain.
3. **Locate and type the Spring/Upthrust** (`knowledge/08` §2.6–2.7): type 1/2/3 for Spring, type 1/2(UTAD)/3(Minor UTAD) for Upthrust, using the book's own volume/reaction/confirmation criteria — never invent a type from a partial match.
4. **Check Effort-vs-Result / SOT** (`knowledge/08` §2.3): does the swing structure show shortening thrusts consistent with the phase call? **If the data source is `mt5_bridge_live`** (commodities), note explicitly that "volume" is tick-count, not real traded size (`docs/architecture/mt5-bridge.md`'s hard caveat) — Effort-vs-Result evidence from this source is weaker than the same read on Binance-sourced crypto data, and should be scored down accordingly, not treated as equivalent.
5. **Score (0–25):** phase clarity (0–8) + Spring/Upthrust type & quality (0–10) + Effort-vs-Result/SOT alignment (0–7). Mark this dimension `eligible: true` only if the exchange market-data source was `AVAILABLE` (not `MOCK`) per `docs/architecture/data-sources.md`.
6. **Cite every claim** — `knowledge/08 pXXX` or the relevant section heading — so DecisionAgent and any later review can verify it.

## Hard rules (inherited, not restated in full — see master spec §25 and §10)

- Never claim a Spring/Upthrust confirmation from a timeframe/data source marked `UNAVAILABLE` or `STALE`.
- Never re-classify the phase after seeing the Confluence Score to make a trade pass (mode-lock discipline, `SYSTEM-DESIGN.md` §6.2).
- If regime is UNCLEAR, reduce this dimension's score rather than assuming RANGING.
