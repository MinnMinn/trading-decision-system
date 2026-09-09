---
name: footprint-skill
description: Use when analyzing order-flow execution confirmation under the institutional trading system — Footprint chart reads (POC, Imbalance, Stacked Imbalance, Absorption/Exhaustion/Development), Delta/Cumulative-Delta divergence, and Tape Reading. Invoked by FlowAgent as part of /analyze and /entry.
---

# FootprintSkill

Answers: **what is actually happening inside the price movement?** Owns the Footprint dimension of the Confluence Score (`docs/architecture/SYSTEM-DESIGN.md` §6, 0–25 points).

Theory lives in `knowledge/01-03` (the dedicated Footprint/Tape-Reading course) and `knowledge/07` §3–4 (the same tools as taught in the Wyckoff-and-Modern-Tools book, including its explicit Wyckoff bridge points). Cite the exact file/section for every claim — never assert an absorption/exhaustion/development read or a Delta divergence strength from memory.

## Procedure

1. **Confirm data availability first.** This skill requires CoinGlass footprint-history data. If that source is `MOCK`/`UNAVAILABLE`/`STALE` (`docs/architecture/data-sources.md`), say so plainly and mark this dimension `eligible: false` — do not infer order-flow confirmation from candle shape alone; that is a candle-shape-only inference and is explicitly the failure mode both source books warn against.
2. **Read the anchor candle/bar** identified by StructureAgent's Spring/Upthrust or ICT structural-break location: POC, R/H/R/L, Imbalance, Stacked Imbalance (`knowledge/03`, `knowledge/07` §3.2). Note the diagonal-comparison rule for Imbalance — never compare BID/ASK horizontally.
3. **Run the Absorption → Exhaustion → Development read** (`knowledge/07` §5, Ch. 10 procedure) — these can interleave; don't force a rigid order if the evidence doesn't fit one.
4. **Check Delta / Cumulative-Delta divergence strength** (`knowledge/07` §3.3): Strong / Medium / Weak / Hidden, per the book's own four-tier framework — a "Strong" divergence at a Spring/UTAD location is the book's own explicit highest-conviction bridge point; cite it as such when present.
5. **Cross-check against Tape Reading** if a clean bar-by-bar or swing-by-swing read is available (`knowledge/02`, `knowledge/07` §4) — this is supporting evidence for the same dimension, not a second independent one.
6. **Score (0–25):** absorption/exhaustion/development read (0–10) + Delta/Cumulative-Delta divergence strength (0–8) + Tape-Reading case alignment (0–7).
7. **Cite every claim.**

## Hard rules

- Never claim Footprint/Delta confirmation when the underlying CoinGlass source is not `AVAILABLE` — a `MOCK`-sourced read may complete a rehearsal analysis but must carry the REHEARSAL MODE banner and cannot make this dimension `eligible` for a live verdict.
- Remember the book's own subjectivity caveat (`knowledge/07` §3.2, "Caveats — subjectivity of column placement"): a BID/ASK print can reflect a position-closing order (stop-loss/take-profit), not fresh directional conviction. Flag this explicitly whenever a large print near a key level could plausibly be exit flow rather than new initiative.
