---
name: footprint-skill
description: Use when analyzing order-flow execution confirmation under the institutional trading system — Footprint chart reads (POC, Imbalance, Stacked Imbalance, Absorption/Exhaustion/Development), Delta/Cumulative-Delta divergence, and Tape Reading. Invoked by FlowAgent as part of /analyze and /entry.
---

# FootprintSkill

Answers: **what is actually happening inside the price movement?** Owns the Footprint dimension of the Confluence Score (`docs/architecture/SYSTEM-DESIGN.md` §6, 0–25 points).

**Theory lives in `knowledge/`, not here.** Footprint mechanics, Delta and the per-instrument imbalance ratios are owned by `knowledge/wyckoff/modern-tools.md` §3–§5 — `knowledge/wyckoff/advance.md` contains no Footprint material at all. `knowledge/footprint/wyckoff-logic.md`–`knowledge/footprint/chart-delta.md` is a second author's Footprint/Tape-Reading course. Tape reading is split across two non-interchangeable frameworks; see step 5. Source precedence: `knowledge/integrated/method.md` §1 and §3.

Cite the exact file and section for every claim. Never assert an absorption/exhaustion/development read or a Delta divergence strength from memory.

## Procedure

1. **Confirm data availability first.** This skill requires CoinGlass footprint-history data. If that source is `MOCK` / `UNAVAILABLE` / `STALE` (`docs/architecture/data-sources.md`), say so plainly and mark this dimension `eligible: false`. Do not infer order flow from candle shape — that is exactly the failure mode both source books name. **Note what does not change:** the Wyckoff dimension is unaffected, because `knowledge/wyckoff/advance.md` §4.1 tape reading, §4.6 SOT and the phase work all run on plain candles (`knowledge/integrated/method.md` §5).
2. **Read the anchor candle/bar** that StructureAgent identified — the Spring/Upthrust or structural-break location. POC, R/H, R/L, Imbalance, Stacked Imbalance (`knowledge/footprint/chart-delta.md`, `knowledge/wyckoff/modern-tools.md` §3.2). Compare imbalance **diagonally**, never horizontally. Imbalance ratios are instrument-specific: roughly 3–4× for gold and oil CFDs, ~3× for stocks, adjusted per token for crypto (`knowledge/wyckoff/modern-tools.md` §3.2, WMT p107–p109).
3. **Run the Absorption → Exhaustion → Development read** (`knowledge/wyckoff/modern-tools.md` §5 Step 5). These can interleave; do not force a rigid order.
4. **Check Delta / Cumulative-Delta divergence strength** — Strong / Medium / Weak / Hidden (`knowledge/wyckoff/modern-tools.md` §3.3). A "Strong" divergence at a Spring or UTAD location is the book's own highest-conviction bridge point (WMT p141); cite it as such when present.
5. **Tape reading — pick the framework by data availability, and name which one you used.** The two are by the same author but are **not interchangeable and their case numbers do not correspond** (`knowledge/wyckoff/advance.md` §8, `knowledge/integrated/method.md` §3.3):
   - `knowledge/wyckoff/modern-tools.md` §4.2 — **10 cases**, axes Volume × Delta × Result. Requires order-flow data. Use when CoinGlass is `AVAILABLE`.
   - `knowledge/wyckoff/advance.md` §4.1 — **5 cases per context** (bối cảnh tăng / bối cảnh giảm), axes spread × volume only, no Delta. Runs on plain candles. This belongs to the **Wyckoff** dimension, not this one — if you cite it here, cite it as corroboration and do not score it twice.
   - Never write "case 3" without naming the framework.
6. **Match the flow read against the expected signature for the Wyckoff event** StructureAgent named (`knowledge/integrated/method.md` §3.2). That table states what would confirm the structural read at each event — and equally what would falsify it. A flow read that contradicts the event is a Contradiction to report, not evidence to discard.
7. **Score (0–25):** absorption/exhaustion/development read (0–10) + Delta/Cumulative-Delta divergence strength (0–8) + tape-reading case alignment (0–7).
8. **Cite every claim.**

## Two different things are called "absorption"

Do not conflate them, and do not count one as confirmation of the other when the second is simply the first zoomed in (`knowledge/integrated/method.md` §3.4):

- **Order-flow absorption** (`knowledge/wyckoff/modern-tools.md` §5 Step 5, `knowledge/wyckoff/modern-tools.md` §3.2) — a large passive order matching repeated active orders at one price without price moving. A single-bar read from footprint data. **This is the one this skill scores.**
- **Structural absorption** (`knowledge/wyckoff/advance.md` §3.2) — hấp thụ chiều ngang (through consolidation, supply gradually decreasing) versus hấp thụ dọc (on the way up, demand spiking). A range-and-swing-level read from candles and volume, owned by the Wyckoff dimension.

Related: **Urgent Demand** (`knowledge/wyckoff/advance.md` §3.3) is a demand spike that negates prior supply. It is not the same as an SOS, and its order-flow signature (stacked ASK imbalance with rapid price gain following slow absorption) is worth checking for explicitly at accumulation lows.

## Hard rules

- Never claim Footprint/Delta confirmation when the underlying CoinGlass source is not `AVAILABLE`. A `MOCK`-sourced read may complete a rehearsal analysis but must carry the REHEARSAL MODE banner and cannot make this dimension `eligible` for a live verdict.
- **Subjectivity caveat, always in force** (`knowledge/wyckoff/modern-tools.md` §3.2, "Caveats — subjectivity of column placement"): a BID/ASK print can reflect a position-closing order (stop-loss or take-profit), not fresh directional conviction. Flag this explicitly whenever a large print near a key level could plausibly be exit flow.
- Real traded volume is required. Tick-count Delta — what FX and most CFD feeds report — is flagged unreliable by the source itself (`knowledge/wyckoff/modern-tools.md` §7). This is a DATA-QUALITY limit, not a permission one: the Forex prohibition was lifted 2026-09-17, so the caveat now has to stand on its own, and it does. It is the same limit that already applies to XAUUSD/XAGUSD through the MT5 bridge (`_volume_caveat`, `analysis-params.json` `tick_volume_credit_multiplier`).
- This dimension counts **once** toward the methodology minimum regardless of how many individual signals it produced (`SYSTEM-DESIGN.md` §6.1). Absorption plus a Delta divergence plus a tape-reading case at the same bar is one dimension's observation, not three.
