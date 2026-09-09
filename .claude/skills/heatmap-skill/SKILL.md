---
name: heatmap-skill
description: Use when analyzing liquidity/positioning under the institutional trading system — liquidation clusters, orderbook liquidity concentration, liquidity sweeps and targets. Invoked by LiquidityAgent as part of /analyze and /entry.
---

# HeatmapSkill

Answers: **where is liquidity positioned, and what may price be attracted to or react against?** Owns the Heatmap dimension of the Confluence Score (`docs/architecture/SYSTEM-DESIGN.md` §6, 0–25 points).

**No ingested knowledge-base source exists for this dimension** (`docs/architecture/data-sources.md`) — unlike the other three skills, this skill's rules come only from the master system prompt's own text (its §2.4 and §8), not from a book/course. Treat this as a standing caveat: this dimension's rules are less independently-verified than the other three until a dedicated source is ingested. Do not compensate by inventing theory — if the master-spec text doesn't cover a case, say "not specified" rather than filling the gap from general knowledge.

## Procedure

1. **Confirm data availability first.** Requires CoinGlass `liquidation-heatmap` and `orderbook-heatmap` endpoints. Note: **these are crypto-derivatives-specific** — for XAUUSD/XAGUSD/USOIL/UKOIL, CoinGlass does not offer this data at all (`docs/architecture/data-sources.md`), so this dimension should be reported `UNAVAILABLE` (not `MOCK`, not silently skipped) for those instruments unless/until a different commodities liquidity data source is integrated.
2. **Read liquidation clusters**: size (`notional_est` — always an estimate, never state it as precise), side, and whether a cluster is `resting` (a forward target/magnet) or `consumed` (already run — do not treat a consumed cluster as a live target).
3. **Read orderbook heatmap**: resting size concentrations by price/side — has a wall rebuilt after a sweep (supporting a reversal read) or is it thinning (supporting continuation)?
4. **Deduplicate before scoring** — a liquidation cluster and an orderbook wall at the *same* price are one underlying phenomenon (concentrated resting liquidity), not two independent observations; per the master spec's explicit example (liquidity sweep + liquidation cluster + orderbook removal = one event), collapse these into a single cited observation for this dimension.
5. **Score (0–25):** liquidity-sweep/target alignment (0–10) + liquidation-cluster interaction (0–8) + orderbook positioning (0–7).
6. **Cite every claim** to the specific CoinGlass fixture/field.

## Hard rules

- Never infer a liquidation cluster's existence from price action alone — it must come from actual heatmap data (`AVAILABLE`, not `MOCK`) to count as `eligible` for a live verdict.
- Never state a `notional_est` figure as a confirmed, precise number in the Trade Plan output — always "an estimated cluster of ~$X."
