---
name: ict-skill
description: Use when analyzing location/setup/structure/timing under the institutional trading system — ICT/TTrades market structure, liquidity, OTE, killzones, PO3/AMD, TTrades models. Invoked by StructureAgent as part of /analyze, /bias, and /entry.
---

# ICTSkill

Answers: **where and when is the setup likely to occur?** Owns the ICT dimension of the Confluence Score (`docs/architecture/SYSTEM-DESIGN.md` §6, 0–25 points).

Theory lives in `knowledge/04-ttrades-core-A.md`, `knowledge/05-ttrades-core-B.md`, and `knowledge/06-ttrades-models.md`. This skill does not restate that theory — cite the exact file/section for every claim.

## Procedure

1. **HTF bias** (`knowledge/04`): Daily/4H structure — is the last confirmed structural break bullish or bearish (MSS/BOS)? Does it agree or conflict with WyckoffSkill's phase call? A conflict here is a candidate Contradiction, not something to quietly drop.
2. **Structure/location quality** (`knowledge/04`–`05`): identify the nearest relevant OB/FVG/Breaker/Mitigation Block, IRL/ERL liquidity, and premium/discount positioning relative to the current dealing range. State the specific level(s), not a vague "near support."
3. **Timing** (`knowledge/04`, killzones/PO3/AMD; `knowledge/06`, TTrades models — OSOK, Fractal, Sons Model, TTRS, Unicorn, Timeframe Alignment): does the current session/killzone and AMD phase support the setup timing? If the setup requires a killzone the current time is outside of, say so — don't imply timing confluence that isn't there.
4. **Score (0–25):** HTF bias alignment (0–8) + structure/location quality (0–10) + timing alignment (0–7). Mark `eligible: true` only if the exchange market-data source was `AVAILABLE` (not `MOCK`).
5. **Cite every claim** — `knowledge/04-06`, section heading or concept name.

## Independence discipline

ICT's job is location/timing — do not double-count a liquidity observation here AND again as the Heatmap dimension if it's the same underlying phenomenon read from the same or equivalent data (e.g. an IRL/ERL liquidity pool inferred from price structure vs. a CoinGlass liquidation cluster at the same price are related but are two genuinely different data sources — cite both if both are real, but flag the overlap explicitly to DecisionAgent so it isn't silently treated as two unrelated confirmations).
